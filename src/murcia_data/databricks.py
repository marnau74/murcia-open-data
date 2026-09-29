"""Carga de la capa bronze en Databricks (segundo destino del proyecto dbt).

La interpretación de las fuentes (JSON del INE, HTML de murciaturistica) vive en un solo
sitio: `murcia_data.bronze`, sobre DuckDB. Para Databricks se exportan esas tablas a
Parquet, se suben a un volume de Unity Catalog y se crean como tablas Delta con
`read_files`. A partir de ahí, `dbt build --target databricks` construye silver y gold con
los mismos modelos que en DuckDB.

Configuración (variables de entorno, nunca en el repositorio):
  DATABRICKS_HOST, DATABRICKS_HTTP_PATH y DATABRICKS_TOKEN, o bien
  DATABRICKS_CONFIG_PROFILE con una sesión de la CLI de Databricks.

Uso: python -m murcia_data.databricks            (carga bronze)
     python -m murcia_data.databricks paridad    (compara gold entre DuckDB y Databricks)
"""

import os
import tempfile
import time
from pathlib import Path

import duckdb

CATALOGO = "murcia_turismo"
VOLUME = f"/Volumes/{CATALOGO}/raw/landing/bronze"
TABLAS_BRONZE = ["ine_series", "murciaturistica_destinos"]
WAREHOUSE = Path(os.environ.get("MURCIA_WAREHOUSE", "data/warehouse.duckdb"))


def id_warehouse(http_path: str) -> str:
    """El id del SQL warehouse es el último tramo de su HTTP path."""
    return http_path.rstrip("/").rsplit("/", 1)[-1]


def sql_crear_tabla(tabla: str) -> str:
    """CREATE OR REPLACE de una tabla Delta de bronze a partir de su Parquet en el volume."""
    return (
        f"CREATE OR REPLACE TABLE {CATALOGO}.bronze.{tabla} "
        f"COMMENT 'Exportada desde bronze.{tabla} de DuckDB (murcia_data.bronze)' "
        f"AS SELECT * FROM read_files('{VOLUME}/{tabla}.parquet', format => 'parquet')"
    )


def exportar_bronze(warehouse: Path, destino: Path) -> dict[str, Path]:
    """Exporta las tablas de bronze de DuckDB a Parquet (solo lectura sobre el warehouse)."""
    ficheros = {}
    with duckdb.connect(str(warehouse), read_only=True) as con:
        for tabla in TABLAS_BRONZE:
            fichero = destino / f"{tabla}.parquet"
            con.execute(f"COPY bronze.{tabla} TO '{fichero.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
            ficheros[tabla] = fichero
    return ficheros


def _ejecutar(cliente, warehouse_id: str, sql: str) -> None:
    """Ejecuta una sentencia en el SQL warehouse y espera a que termine."""
    from databricks.sdk.service.sql import StatementState

    respuesta = cliente.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="50s"
    )
    while respuesta.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        respuesta = cliente.statement_execution.get_statement(respuesta.statement_id)
    if respuesta.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Falló en Databricks: {sql[:80]}… → {respuesta.status.error}")


def cargar(warehouse: Path = WAREHOUSE, cliente=None) -> dict[str, int]:
    """Sube bronze a Databricks y devuelve las filas de cada tabla creada."""
    from databricks.sdk import WorkspaceClient

    cliente = cliente or WorkspaceClient()
    warehouse_id = id_warehouse(os.environ["DATABRICKS_HTTP_PATH"])
    filas = {}
    with tempfile.TemporaryDirectory() as tmp:
        for tabla, fichero in exportar_bronze(warehouse, Path(tmp)).items():
            with fichero.open("rb") as contenido:
                cliente.files.upload(f"{VOLUME}/{tabla}.parquet", contenido, overwrite=True)
            _ejecutar(cliente, warehouse_id, sql_crear_tabla(tabla))
            with duckdb.connect(str(warehouse), read_only=True) as con:
                (filas[tabla],) = con.execute(f"SELECT count(*) FROM bronze.{tabla}").fetchone()
    return filas


def sql_huella(tabla: str, columnas: list[tuple[str, str]], prefijo: str) -> str:
    """Filas y suma de cada columna numérica de una tabla: su «huella» para comparar
    motores. Las sumas se redondean para no confundir diferencias de coma flotante."""
    numericas = [c for c, tipo in columnas if tipo.upper() in TIPOS_NUMERICOS]
    sumas = "".join(f", round(sum({c}), 4) AS suma_{c}" for c in numericas)
    return f"SELECT count(*) AS filas{sumas} FROM {prefijo}.{tabla}"


TIPOS_NUMERICOS = {"SMALLINT", "INTEGER", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT"}


def _consultar(cliente, warehouse_id: str, sql: str) -> list:
    from databricks.sdk.service.sql import StatementState

    respuesta = cliente.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="50s"
    )
    while respuesta.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        respuesta = cliente.statement_execution.get_statement(respuesta.statement_id)
    if respuesta.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Falló en Databricks: {sql[:80]}… → {respuesta.status.error}")
    return respuesta.result.data_array[0]


def comparar_gold(warehouse: Path = WAREHOUSE, cliente=None) -> dict[str, dict]:
    """Compara la huella de cada tabla de gold en DuckDB y en Databricks. Devuelve solo
    las tablas que difieren (vacío = paridad completa)."""
    from databricks.sdk import WorkspaceClient

    cliente = cliente or WorkspaceClient()
    warehouse_id = id_warehouse(os.environ["DATABRICKS_HTTP_PATH"])
    diferencias = {}
    with duckdb.connect(str(warehouse), read_only=True) as con:
        tablas = [
            t for (t,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'gold'").fetchall()
        ]
        for tabla in sorted(tablas):
            columnas = con.execute(
                "SELECT column_name, data_type FROM duckdb_columns() WHERE schema_name = 'gold' AND table_name = ?",
                [tabla],
            ).fetchall()
            local = [
                float(v) if v is not None else None for v in con.execute(sql_huella(tabla, columnas, "gold")).fetchone()
            ]
            remoto = [
                float(v) if v is not None else None
                for v in _consultar(cliente, warehouse_id, sql_huella(tabla, columnas, f"{CATALOGO}.gold"))
            ]
            if local != remoto:
                diferencias[tabla] = {"duckdb": local, "databricks": remoto}
    return diferencias


def main() -> None:
    filas = cargar()
    print(" · ".join(f"{CATALOGO}.bronze.{t}: {n} filas" for t, n in filas.items()))


def paridad() -> None:
    diferencias = comparar_gold()
    if diferencias:
        raise SystemExit(f"Gold difiere entre DuckDB y Databricks: {diferencias}")
    print("Paridad completa: gold es idéntico en DuckDB y en Databricks")


if __name__ == "__main__":
    import sys

    paridad() if sys.argv[1:] == ["paridad"] else main()
