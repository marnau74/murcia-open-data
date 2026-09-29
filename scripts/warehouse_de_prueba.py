"""Crea un warehouse pequeño a partir de los fixtures de tests/, para ejecutar
`dbt build` en la CI sin llamar a las fuentes.

Uso: uv run python scripts/warehouse_de_prueba.py data/warehouse_ci.duckdb
"""

import shutil
import sys
import tempfile
from pathlib import Path

from murcia_data.bronze import cargar_ine, cargar_murciaturistica, conectar

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures"


def main(destino: str) -> None:
    Path(destino).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp)
        ine = raw / "ine" / "2026-09-29"
        ine.mkdir(parents=True)
        for fixture in (FIXTURES / "ine").glob("serie_*.json"):
            shutil.copy(fixture, ine / fixture.name.removeprefix("serie_"))
        shutil.copytree(FIXTURES / "murciaturistica", raw / "murciaturistica")
        with conectar(destino) as con:
            print(f"ine: {cargar_ine(con, raw)} filas · murciaturistica: {cargar_murciaturistica(con, raw)} filas")


if __name__ == "__main__":
    main(sys.argv[1])
