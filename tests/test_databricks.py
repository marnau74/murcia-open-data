"""Tests de la carga en Databricks, sin conexión: funciones puras y un cliente falso."""

from types import SimpleNamespace

import duckdb
import pytest

from murcia_data.databricks import (
    CATALOGO,
    VOLUME,
    exportar_bronze,
    id_warehouse,
    sql_crear_tabla,
    sql_huella,
)


@pytest.fixture
def warehouse(tmp_path):
    ruta = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(ruta)) as con:
        con.execute("CREATE SCHEMA bronze")
        con.execute("CREATE TABLE bronze.ine_series AS SELECT 'EOT1' AS codigo, 2024::SMALLINT AS anio, 10.5 AS valor")
        con.execute(
            "CREATE TABLE bronze.murciaturistica_destinos AS SELECT 'La Manga' AS destino, 7::BIGINT AS viajeros"
        )
    return ruta


def test_id_warehouse_es_el_ultimo_tramo_del_http_path():
    assert id_warehouse("/sql/1.0/warehouses/0123456789abcdef") == "0123456789abcdef"
    assert id_warehouse("/sql/1.0/warehouses/abc/") == "abc"


def test_sql_crear_tabla_lee_el_parquet_del_volume():
    sql = sql_crear_tabla("ine_series")
    assert sql.startswith(f"CREATE OR REPLACE TABLE {CATALOGO}.bronze.ine_series")
    assert f"read_files('{VOLUME}/ine_series.parquet', format => 'parquet')" in sql


def test_la_huella_suma_solo_las_columnas_numericas():
    sql = sql_huella("fct", [("fecha_id", "INTEGER"), ("territorio_id", "VARCHAR"), ("viajeros", "BIGINT")], "gold")
    assert sql == (
        "SELECT count(*) AS filas, round(sum(fecha_id), 4) AS suma_fecha_id, "
        "round(sum(viajeros), 4) AS suma_viajeros FROM gold.fct"
    )


def test_exportar_bronze_genera_un_parquet_por_tabla(warehouse, tmp_path):
    ficheros = exportar_bronze(warehouse, tmp_path)
    assert set(ficheros) == {"ine_series", "murciaturistica_destinos"}
    with duckdb.connect() as con:
        fila = con.execute(f"SELECT * FROM '{ficheros['ine_series'].as_posix()}'").fetchone()
    assert fila == ("EOT1", 2024, 10.5)


def test_cargar_sube_los_ficheros_y_crea_las_tablas(warehouse, monkeypatch):
    pytest.importorskip("databricks.sdk")
    from databricks.sdk.service.sql import StatementState

    from murcia_data.databricks import cargar

    subidos, sentencias = [], []

    class Ficheros:
        def upload(self, ruta, contenido, overwrite):
            subidos.append((ruta, len(contenido.read()), overwrite))

    class Sentencias:
        def execute_statement(self, warehouse_id, statement, wait_timeout):
            sentencias.append((warehouse_id, statement))
            return SimpleNamespace(status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None))

    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
    filas = cargar(warehouse, cliente=SimpleNamespace(files=Ficheros(), statement_execution=Sentencias()))

    assert filas == {"ine_series": 1, "murciaturistica_destinos": 1}
    assert [ruta for ruta, _, _ in subidos] == [
        f"{VOLUME}/ine_series.parquet",
        f"{VOLUME}/murciaturistica_destinos.parquet",
    ]
    assert all(tamano > 0 and sobrescribe for _, tamano, sobrescribe in subidos)
    assert [w for w, _ in sentencias] == ["abc", "abc"]
    assert sentencias[0][1] == sql_crear_tabla("ine_series")
