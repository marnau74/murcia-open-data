"""Regenera el catálogo de series del INE (dbt/seeds/series_ine.csv).

Se ejecuta a mano cuando se quieren añadir tablas o revisar el catálogo, no en cada
ejecución del pipeline. El resultado se revisa con `git diff` antes de hacer commit.

Uso: uv run python scripts/generar_catalogo_ine.py
"""

import csv
from pathlib import Path

from murcia_data.ingest.catalogo_ine import COLUMNAS, TABLAS, construir_catalogo
from murcia_data.ingest.ine import IneClient

SALIDA = Path("dbt/seeds/series_ine.csv")


def main() -> None:
    cliente = IneClient()
    metadatos = {tabla.id: cliente.metadatos_tabla(tabla.id) for tabla in TABLAS}
    filas = construir_catalogo(metadatos)
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"{len(filas)} series en {SALIDA}")


if __name__ == "__main__":
    main()
