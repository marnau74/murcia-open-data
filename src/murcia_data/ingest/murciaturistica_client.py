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
import time
from pathlib import Path

import pandas as pd
import requests

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
        self.session = requests.Session()
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

    def _descargar_html(self, anio: int, mes: int) -> bytes:
        cache_file = self.cache_dir / f"destinos_{anio}-{mes:02d}.html"
        if cache_file.exists():
            return cache_file.read_bytes()
        resp = self.session.get(self._url(anio, mes), timeout=30)
        resp.raise_for_status()
        cache_file.write_bytes(resp.content)
        time.sleep(self.pausa)
        return resp.content

    def viajeros_pernoctaciones_por_destino(self, anio: int, mes: int) -> pd.DataFrame:
        """Tabla cruda de un mes: una fila por destino/subtotal, tal cual la
        publica la fuente (incluye subtotales de zona y filas en blanco)."""
        tabla = parsear_tabla(self._descargar_html(anio, mes), anio, mes)
        if tabla[COLUMNAS[1:]].fillna(0).eq(0).all().all():
            # Mes aún sin publicar (la fuente lo devuelve todo a 0): no se
            # deja en caché para volver a pedirlo en la siguiente ejecución.
            (self.cache_dir / f"destinos_{anio}-{mes:02d}.html").unlink(missing_ok=True)
        return tabla

    def serie(self, anio_inicio: int, mes_inicio: int, anio_fin: int, mes_fin: int) -> pd.DataFrame:
        """Concatena la tabla cruda mes a mes (una petición por mes, cacheada)."""
        periodos = []
        anio, mes = anio_inicio, mes_inicio
        while (anio, mes) <= (anio_fin, mes_fin):
            periodos.append((anio, mes))
            mes += 1
            if mes > 12:
                mes, anio = 1, anio + 1
        return pd.concat(
            [self.viajeros_pernoctaciones_por_destino(a, m) for a, m in periodos],
            ignore_index=True,
        )


if __name__ == "__main__":
    # Sesión de exploración manual: un mes de muestra.
    cliente = MurciaturisticaClient()
    print(cliente.viajeros_pernoctaciones_por_destino(2019, 7))
