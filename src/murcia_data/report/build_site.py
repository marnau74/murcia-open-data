"""Genera la web estática del informe (site/index.html) a partir de la capa gold.

La página es una plantilla HTML con los datos incrustados como JSON: no hay servidor ni
base de datos, y cualquier cifra que aparece en ella sale de
murcia_data/report/indicadores.py.

Uso: python -m murcia_data.report.build_site
"""

import json
import os
from datetime import date
from pathlib import Path

import duckdb

from murcia_data.report.indicadores import calcular

PLANTILLA = Path(__file__).with_name("plantilla.html")
SALIDA = Path("site")
MARCADOR = "/*__DATOS__*/null"


def construir_datos(warehouse: str) -> dict:
    with duckdb.connect(warehouse, read_only=True) as con:
        return {"generado": date.today().isoformat(), **calcular(con)}


def generar(warehouse: str, salida: Path = SALIDA) -> Path:
    datos = construir_datos(warehouse)
    html = PLANTILLA.read_text(encoding="utf-8")
    if MARCADOR not in html:
        raise ValueError("La plantilla no tiene el marcador de datos")
    html = html.replace(MARCADOR, json.dumps(datos, ensure_ascii=False, default=str))
    salida.mkdir(exist_ok=True)
    destino = salida / "index.html"
    destino.write_text(html, encoding="utf-8")
    return destino


def main() -> None:
    warehouse = os.environ.get("MURCIA_WAREHOUSE", "data/warehouse.duckdb")
    destino = generar(warehouse)
    print(f"Web generada en {destino} a partir de {warehouse}")


if __name__ == "__main__":
    main()
