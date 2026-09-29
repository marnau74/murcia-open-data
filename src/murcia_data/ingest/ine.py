"""Cliente de la API JSON del INE (servicios.ine.es/wstempus), de solo lectura.

Fuente: encuestas de ocupación en alojamientos turísticos (EOH hoteles, EOAP
apartamentos, EOAC campings, EOTR turismo rural) y el índice de precios hoteleros
(IPH). Detalles de la API relevantes para este proyecto:

  - Se ingiere por **código de serie** (p. ej. EOT1772), no por tabla: los ids de
    tabla cambian cuando el INE reorganiza su web; los códigos de serie son estables.
  - `DATOS_SERIE/{codigo}?date=AAAAMMDD:` devuelve la serie desde esa fecha hasta el
    último dato publicado, con una marca de secreto estadístico y el tipo de dato
    (definitivo o provisional). Los provisionales se revisan: por eso cada ejecución
    vuelve a descargar la serie entera (una petición por serie).
  - `DATOS_TABLA/{id}?nult=1&tip=AM` devuelve los metadatos estructurados de todas las
    series de una tabla (territorio, concepto, residencia...). Se usa solo para generar
    el catálogo de series (scripts/generar_catalogo_ine.py), no en cada ejecución.

Uso: python -m murcia_data.ingest.ine  (descarga todas las series del catálogo)

Este módulo solo trae datos: guarda las respuestas tal cual en la capa raw. La
interpretación se hace en bronze y dbt.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://servicios.ine.es/wstempus/js/ES"
INICIO_SERIE = date(2015, 1, 1)


def _sesion_con_reintentos() -> requests.Session:
    """Sesión HTTP con reintentos y espera exponencial ante errores transitorios."""
    reintentos = Retry(
        total=5,
        backoff_factor=1.0,  # 0 s, 2 s, 4 s, 8 s, 16 s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    sesion = requests.Session()
    sesion.mount("https://", HTTPAdapter(max_retries=reintentos))
    sesion.headers["User-Agent"] = "murcia-open-data (+https://github.com/marnau74/murcia-open-data)"
    return sesion


class IneClient:
    """Cliente de solo lectura para la API del INE."""

    def __init__(self, sesion: requests.Session | None = None, pausa: float = 0.3, timeout: float = 30):
        self.sesion = sesion or _sesion_con_reintentos()
        self.pausa = pausa
        self.timeout = timeout

    def _get(self, ruta: str, params: dict | None = None) -> dict | list:
        resp = self.sesion.get(f"{BASE_URL}/{ruta}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        time.sleep(self.pausa)
        return resp.json()

    def serie(self, codigo: str, desde: date = INICIO_SERIE) -> dict:
        """Serie completa desde `desde` hasta el último dato publicado."""
        datos = self._get(f"DATOS_SERIE/{codigo}", {"date": f"{desde:%Y%m%d}:"})
        if not isinstance(datos, dict) or datos.get("COD") != codigo:
            raise ValueError(f"Respuesta inesperada del INE para la serie {codigo}")
        return datos

    def metadatos_tabla(self, tabla_id: int) -> list[dict]:
        """Metadatos estructurados de todas las series de una tabla (último dato incluido)."""
        datos = self._get(f"DATOS_TABLA/{tabla_id}", {"nult": 1, "tip": "AM"})
        if not isinstance(datos, list):
            raise ValueError(f"Respuesta inesperada del INE para la tabla {tabla_id}")
        return datos


def ingerir_series(
    cliente: IneClient,
    codigos: list[str],
    raw_dir: Path,
    fecha_ingesta: date,
    desde: date = INICIO_SERIE,
) -> list[Path]:
    """Descarga cada serie y guarda la respuesta tal cual en
    `raw_dir/<fecha_ingesta>/<codigo>.json`. La capa raw es inmutable: si el fichero
    ya existe para esa fecha de ingesta, no se vuelve a pedir."""
    destino = raw_dir / fecha_ingesta.isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    ficheros = []
    for codigo in codigos:
        fichero = destino / f"{codigo}.json"
        if not fichero.exists():
            respuesta = cliente.serie(codigo, desde)
            temporal = fichero.with_suffix(".tmp")
            temporal.write_text(json.dumps(respuesta, ensure_ascii=False), encoding="utf-8")
            temporal.replace(fichero)  # escritura atómica: nunca queda un JSON a medias
        ficheros.append(fichero)
    return ficheros


def codigos_del_catalogo(seed: Path) -> list[str]:
    """Códigos de serie del catálogo versionado (dbt/seeds/series_ine.csv)."""
    with seed.open(encoding="utf-8") as f:
        return [fila["codigo"] for fila in csv.DictReader(f)]


def main() -> None:
    codigos = codigos_del_catalogo(Path("dbt/seeds/series_ine.csv"))
    ficheros = ingerir_series(IneClient(), codigos, Path("data/raw/ine"), fecha_ingesta=date.today())
    print(f"{len(ficheros)} series del INE en {ficheros[0].parent}")


if __name__ == "__main__":
    main()
