"""Cliente para las estadísticas de turismo de la Región de Murcia
(murciaturistica.es), reprocesadas por el CREM a partir de la Encuesta de
Ocupación Hotelera (EOH) del INE.

Fuente elegida tras la sesión de exploración: el INE en bruto solo distingue
Cartagena / Murcia capital / Costa Cálida, y los portales CKAN
(datosabiertos.regiondemurcia.es, transparencia.mimurcia.murcia.es) no
publican series de demanda turística (el primero solo tiene directorios de
establecimientos; el segundo es inalcanzable). Este portal sí publica la
serie mensual desglosada en los 11 "destinos turísticos" oficiales,
agrupados en Ciudad / Costa / Interior.

Detalles del endpoint (descubiertos navegando la web con un navegador real,
no documentados en ninguna API):
  - La URL termina en ".xls" pero el contenido es HTML; hay que parsearlo
    con pandas.read_html, no con un lector de Excel.
  - Sin cabecera Referer apuntando a la página real, responde 404.
  - El parámetro "parametros" usa '$' y '=' literales sin codificar; si se
    pasa como dict a requests (que los porcentualiza), el servidor también
    devuelve 404. Hay que construir la URL a mano.
  - Pidiendo un rango de varios meses, el servidor DEVUELVE EL AGREGADO del
    rango, no una fila por mes. Para la serie mensual hay que pedir mes a
    mes (ver `serie`).
  - Algunas celdas de un destino individual aparecen a 0 cuando el grado de
    respuesta de las encuestas es bajo (secreto estadístico), pero el
    subtotal de zona publicado sigue siendo el valor real. La tabla cruda
    se devuelve tal cual la publica la fuente, incluidos subtotales y filas
    en blanco; el filtrado a destinos-hoja se hace en la capa de transform.
"""

from __future__ import annotations

import io
import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from murcia_data.ingest.http import sesion_con_reintentos

log = logging.getLogger(__name__)

BASE_URL = "https://www.murciaturistica.es/es/descargas.xls"
PAGINA = "viajeros-y-pernoctaciones-segun-destinos"
REFERER = f"https://www.turismoregiondemurcia.es/es/estadisticas_de_turismo?pagina={PAGINA}"

COLUMNAS = [
    "destino",
    "viajeros_total",
    "viajeros_residentes",
    "viajeros_no_residentes",
    "pernoctaciones_total",
    "pernoctaciones_residentes",
    "pernoctaciones_no_residentes",
]


INICIO_SERIE = (2015, 1)

# Los últimos meses pedidos se vuelven a descargar aunque estén en la caché: la fuente
# publica con unos dos meses de retraso (un mes que hoy viene a 0 puede publicarse luego)
# y puede revisar los recientes. Los anteriores ya no cambian y salen de la caché.
REVISAR_ULTIMOS = 6


def mes_anterior(hoy: date) -> tuple[int, int]:
    """Último mes que se pide a la fuente: el anterior al actual. Los meses que aún no se
    han publicado vuelven enteros a 0 y se descartan después (en silver), así que pedir de
    más no falsea nada y permite recoger datos nuevos en cuanto aparecen."""
    return (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)


def parsear_tabla(contenido: bytes, anio: int, mes: int) -> pd.DataFrame:
    """Interpreta el HTML de un mes: una fila por destino o subtotal, tal cual la
    publica la fuente (incluye subtotales de zona y filas en blanco). Función pura:
    la usan el cliente y la carga de bronze, que trabaja sobre la capa raw sin red."""
    tabla = pd.read_html(io.BytesIO(contenido))[0]
    tabla = tabla.iloc[2:].reset_index(drop=True)  # filas 0 y 1 son cabecera
    tabla.columns = COLUMNAS
    for columna in COLUMNAS[1:]:
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce")
    tabla.insert(0, "mes", mes)
    tabla.insert(0, "anio", anio)
    return tabla


class MurciaturisticaClient:
    """Cliente de solo lectura para la serie de viajeros/pernoctaciones por destino."""

    def __init__(self, cache_dir: str | Path = "data/raw/murciaturistica", pausa: float = 0.5):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pausa = pausa
        self.session = sesion_con_reintentos()
        # El portal responde 404 sin un Referer de su propia web; el User-Agent de
        # navegador es el que se usó al descubrir el endpoint.
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; murcia-open-data/0.1; portfolio)",
                "Referer": REFERER,
            }
        )

    def _url(self, anio: int, mes: int) -> str:
        mm = f"{mes:02d}"
        parametros = f"mes_inicio={mm}$mes_fin={mm}$ano_inicio={anio}$ano_fin={anio}$pagina={PAGINA}$descargar=si"
        return f"{BASE_URL}?url={PAGINA}&parametros={parametros}"

    def _descargar_html(self, anio: int, mes: int, revisar: bool = False) -> bytes:
        """El HTML de un mes: de la caché o, si no está o hay que revisarlo, de la fuente. Se
        guarda tal cual, también si viene vacío (un mes aún sin publicar): así no se vuelve a
        pedir en cada ejecución cuando ya no puede cambiar. Si la revisión de un mes que ya
        estaba en la caché falla, se sigue con la copia anterior."""
        cache_file = self.cache_dir / f"destinos_{anio}-{mes:02d}.html"
        if cache_file.exists() and not revisar:
            return cache_file.read_bytes()
        try:
            resp = self.session.get(self._url(anio, mes), timeout=30)
            resp.raise_for_status()
        except requests.RequestException as error:
            if not cache_file.exists():
                raise
            log.warning("No se ha podido revisar %d-%02d: se usa la copia anterior (%s)", anio, mes, error)
            return cache_file.read_bytes()
        temporal = cache_file.with_suffix(".tmp")
        temporal.write_bytes(resp.content)
        temporal.replace(cache_file)  # escritura atómica: nunca queda un HTML a medias en la caché
        time.sleep(self.pausa)
        return resp.content

    def viajeros_pernoctaciones_por_destino(self, anio: int, mes: int, revisar: bool = False) -> pd.DataFrame:
        """Tabla cruda de un mes: una fila por destino/subtotal, tal cual la
        publica la fuente (incluye subtotales de zona y filas en blanco). Un mes sin
        publicar viene entero a 0 y se descarta en silver (int_mt__meses_publicados)."""
        return parsear_tabla(self._descargar_html(anio, mes, revisar), anio, mes)

    def serie(self, anio_inicio: int, mes_inicio: int, anio_fin: int, mes_fin: int) -> pd.DataFrame:
        """Concatena la tabla cruda mes a mes (una petición por mes, cacheada). Los últimos
        `REVISAR_ULTIMOS` meses se vuelven a pedir siempre."""
        periodos = []
        anio, mes = anio_inicio, mes_inicio
        while (anio, mes) <= (anio_fin, mes_fin):
            periodos.append((anio, mes))
            mes += 1
            if mes > 12:
                mes, anio = 1, anio + 1
        revisar = set(periodos[-REVISAR_ULTIMOS:])
        return pd.concat(
            [self.viajeros_pernoctaciones_por_destino(a, m, (a, m) in revisar) for a, m in periodos],
            ignore_index=True,
        )


if __name__ == "__main__":
    # Sesión de exploración manual: un mes de muestra.
    cliente = MurciaturisticaClient()
    print(cliente.viajeros_pernoctaciones_por_destino(2019, 7))
