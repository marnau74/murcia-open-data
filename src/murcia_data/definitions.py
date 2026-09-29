"""Orquestación con Dagster (ver docs/adr/0002-dagster-como-orquestador.md).

Cada tabla o conjunto de ficheros es un *asset* y Dagster deduce el orden por sus
dependencias:

    raw_ine ──────────────► bronze/ine_series ─────────────┐
    raw_murciaturistica ──► bronze/murciaturistica_destinos ┴─► modelos dbt (silver, gold)

Los modelos de dbt se cargan desde su manifest: cada modelo y seed es un asset y cada test
de dbt es una comprobación (*asset check*), así que el linaje va de la API del INE al
mart final en un solo grafo.

En local: `uv run dagster dev` (interfaz en http://localhost:3000).
Sin servidor (CI): `uv run dagster job execute -m murcia_data.definitions -j pipeline_mensual`.
"""

import csv
import os
import shutil
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import dagster as dg
import duckdb
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from murcia_data import bronze
from murcia_data.ingest.ine import IneClient, codigos_del_catalogo, ingerir_series
from murcia_data.ingest.murciaturistica_client import INICIO_SERIE, MurciaturisticaClient, mes_anterior

RAIZ = Path(__file__).resolve().parents[2]

# dbt lee la ruta del warehouse de MURCIA_WAREHOUSE (dbt/profiles.yml) y se ejecuta con
# dbt/ como directorio de trabajo: se fija una ruta absoluta para que Python y dbt
# escriban siempre en el mismo fichero.
os.environ.setdefault("MURCIA_WAREHOUSE", str(RAIZ / "data" / "warehouse.duckdb"))

DBT_PROYECTO = DbtProject(project_dir=RAIZ / "dbt", profiles_dir=RAIZ / "dbt")
DBT_PROYECTO.prepare_if_dev()
if not DBT_PROYECTO.manifest_path.exists():
    # Fuera de `dagster dev` (tests, CI) el manifest se genera con dbt parse.
    from dbt.cli.main import dbtRunner

    resultado = dbtRunner().invoke(
        ["parse", "--quiet", "--project-dir", str(DBT_PROYECTO.project_dir), "--profiles-dir", str(RAIZ / "dbt")]
    )
    if not resultado.success:
        raise RuntimeError(f"dbt parse ha fallado: {resultado.exception}")


def _ejecutable_dbt() -> str:
    """El dbt del mismo entorno que este Python, aunque el entorno no esté activado."""
    junto_a_python = shutil.which("dbt", path=str(Path(sys.executable).parent))
    return junto_a_python or "dbt"


class Rutas(dg.ConfigurableResource):
    """Dónde están la capa raw, el warehouse y el catálogo del INE. Los tests las apuntan
    a directorios temporales."""

    raw: str = str(RAIZ / "data" / "raw")
    warehouse: str = os.environ["MURCIA_WAREHOUSE"]
    catalogo_ine: str = str(RAIZ / "dbt" / "seeds" / "series_ine.csv")


# --- Ingesta (raw) --------------------------------------------------------------------


@dg.asset(group_name="raw", kinds={"python"})
def raw_ine(rutas: Rutas) -> dg.MaterializeResult:
    """Respuestas de la API del INE para todas las series del catálogo (una por serie)."""
    codigos = codigos_del_catalogo(Path(rutas.catalogo_ine))
    ficheros = ingerir_series(IneClient(), codigos, Path(rutas.raw) / "ine", fecha_ingesta=date.today())
    return dg.MaterializeResult(metadata={"series": len(ficheros), "carpeta": str(ficheros[0].parent)})


@dg.asset(group_name="raw", kinds={"python"})
def raw_murciaturistica(rutas: Rutas) -> dg.MaterializeResult:
    """Tablas mensuales de murciaturistica.es. Los meses ya descargados salen de la caché y
    los que la fuente aún no publica no se guardan."""
    carpeta = Path(rutas.raw) / "murciaturistica"
    MurciaturisticaClient(cache_dir=carpeta).serie(*INICIO_SERIE, *mes_anterior(date.today()))
    meses = sorted(carpeta.glob("destinos_*.html"))
    return dg.MaterializeResult(metadata={"meses_publicados": len(meses), "ultimo": meses[-1].stem})


# --- Bronze ---------------------------------------------------------------------------
# Las claves coinciden con las fuentes de dbt (source('bronze', ...)), así Dagster une
# el grafo de Python con el de dbt.


@dg.asset(key=["bronze", "ine_series"], deps=[raw_ine], group_name="bronze", kinds={"duckdb"})
def bronze_ine_series(rutas: Rutas) -> dg.MaterializeResult:
    """Última ingesta del INE en DuckDB, tipada y con columnas de auditoría."""
    with bronze.conectar(rutas.warehouse) as con:
        filas = bronze.cargar_ine(con, Path(rutas.raw))
    return dg.MaterializeResult(metadata={"filas": filas})


@dg.asset(
    key=["bronze", "murciaturistica_destinos"],
    deps=[raw_murciaturistica],
    group_name="bronze",
    kinds={"duckdb"},
)
def bronze_murciaturistica_destinos(rutas: Rutas) -> dg.MaterializeResult:
    """Tablas de murciaturistica en DuckDB, tal cual se publican."""
    with bronze.conectar(rutas.warehouse) as con:
        filas = bronze.cargar_murciaturistica(con, Path(rutas.raw))
    return dg.MaterializeResult(metadata={"filas": filas})


@dg.asset_check(asset=bronze_ine_series, blocking=True)
def ine_catalogo_completo(rutas: Rutas) -> dg.AssetCheckResult:
    """Todas las series del catálogo están en bronze. Si falta alguna, no se construye
    nada aguas abajo (blocking)."""
    with Path(rutas.catalogo_ine).open(encoding="utf-8") as f:
        catalogo = {fila["codigo"] for fila in csv.DictReader(f)}
    with duckdb.connect(rutas.warehouse, read_only=True) as con:
        cargadas = {codigo for (codigo,) in con.execute("SELECT DISTINCT codigo FROM bronze.ine_series").fetchall()}
    faltan = sorted(catalogo - cargadas)
    return dg.AssetCheckResult(passed=not faltan, metadata={"faltan": len(faltan), "ejemplos": faltan[:10]})


@dg.asset_check(asset=bronze_ine_series)
def ine_datos_recientes(rutas: Rutas) -> dg.AssetCheckResult:
    """El INE publica cada mes con uno o dos meses de retraso. Si el último dato tiene más
    de cuatro meses, algo ha cambiado en la fuente: se avisa sin bloquear."""
    with duckdb.connect(rutas.warehouse, read_only=True) as con:
        (ultimo,) = con.execute("SELECT max(make_date(anio, periodo, 1)) FROM bronze.ine_series").fetchone()
    hoy = date.today()
    meses = (hoy.year - ultimo.year) * 12 + hoy.month - ultimo.month
    return dg.AssetCheckResult(
        passed=meses <= 4,
        severity=dg.AssetCheckSeverity.WARN,
        metadata={"ultimo_mes": ultimo.isoformat(), "meses_de_retraso": meses},
    )


# --- dbt (silver y gold) --------------------------------------------------------------


class Traductor(DagsterDbtTranslator):
    """Agrupa los assets de dbt por capa, como en el warehouse."""

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        if dbt_resource_props["resource_type"] == "seed":
            return "referencia"
        carpeta = dbt_resource_props["fqn"][1]
        return {"staging": "silver", "intermediate": "silver", "marts": "gold"}.get(carpeta)


@dbt_assets(manifest=DBT_PROYECTO.manifest_path, project=DBT_PROYECTO, dagster_dbt_translator=Traductor())
def modelos_dbt(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    """Seeds, modelos y tests de dbt: cada test se registra como comprobación del asset."""
    yield from dbt.cli(["build"], context=context).stream()


# --- Trabajo y programación -----------------------------------------------------------

pipeline_mensual = dg.define_asset_job(
    "pipeline_mensual",
    selection=dg.AssetSelection.all(),
    description="Ingesta de las dos fuentes, carga en bronze y construcción de silver y gold.",
)

# El INE publica los datos de un mes a finales del mes siguiente: el día 3 ya están.
ejecucion_mensual = dg.ScheduleDefinition(
    job=pipeline_mensual,
    cron_schedule="0 7 3 * *",
    execution_timezone="Europe/Madrid",
)

defs = dg.Definitions(
    assets=[raw_ine, raw_murciaturistica, bronze_ine_series, bronze_murciaturistica_destinos, modelos_dbt],
    asset_checks=[ine_catalogo_completo, ine_datos_recientes],
    jobs=[pipeline_mensual],
    schedules=[ejecucion_mensual],
    resources={"rutas": Rutas(), "dbt": DbtCliResource(project_dir=DBT_PROYECTO, dbt_executable=_ejecutable_dbt())},
)
