"""Tests del paquete de datos que se publica en cada release."""

import hashlib
import json

import duckdb
import pytest

from murcia_data.release import NOMBRE_DUCKDB, VERSION_CONTRATO, exportar


@pytest.fixture
def warehouse(tmp_path):
    """Warehouse mínimo con dos tablas en gold y una en silver (que no debe publicarse)."""
    ruta = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(ruta)) as con:
        con.execute("CREATE SCHEMA gold")
        con.execute("CREATE SCHEMA silver")
        con.execute(
            "CREATE TABLE gold.fct_demanda_mensual AS "
            "SELECT * FROM (VALUES (201501, 100::BIGINT), (202608, 250::BIGINT)) AS t(fecha_id, pernoctaciones)"
        )
        con.execute("CREATE TABLE gold.dim_residencia AS SELECT 'espana' AS residencia_id")
        con.execute("CREATE TABLE silver.intermedia AS SELECT 1 AS x")
    return ruta


def test_exporta_solo_gold_en_parquet_y_duckdb(warehouse, tmp_path):
    salida = tmp_path / "release"
    exportar(warehouse, salida)

    ficheros = {f.name for f in salida.iterdir()}
    assert ficheros == {
        "fct_demanda_mensual.parquet",
        "dim_residencia.parquet",
        NOMBRE_DUCKDB,
        "contrato.json",
        "SHA256SUMS",
    }
    with duckdb.connect(str(salida / NOMBRE_DUCKDB), read_only=True) as con:
        tablas = con.execute("SELECT schema_name, table_name FROM duckdb_tables() ORDER BY 2").fetchall()
        assert tablas == [("gold", "dim_residencia"), ("gold", "fct_demanda_mensual")]
        parquet = (salida / "fct_demanda_mensual.parquet").as_posix()
        assert con.execute(f"SELECT sum(pernoctaciones) FROM '{parquet}'").fetchone() == (350,)


def test_el_contrato_describe_tablas_columnas_y_periodo(warehouse, tmp_path):
    contrato = exportar(warehouse, tmp_path / "release")

    assert contrato["version_contrato"] == VERSION_CONTRATO
    assert contrato["periodo"] == {"desde": "2015-01", "hasta": "2026-08"}
    demanda = contrato["tablas"]["fct_demanda_mensual"]
    assert demanda["filas"] == 2
    assert demanda["columnas"] == [
        {"nombre": "fecha_id", "tipo": "INTEGER"},
        {"nombre": "pernoctaciones", "tipo": "BIGINT"},
    ]
    guardado = json.loads((tmp_path / "release" / "contrato.json").read_text(encoding="utf-8"))
    assert guardado == contrato


def test_las_sumas_de_verificacion_cuadran(warehouse, tmp_path):
    salida = tmp_path / "release"
    exportar(warehouse, salida)

    lineas = (salida / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 4  # todo salvo el propio SHA256SUMS
    for linea in lineas:
        suma, nombre = linea.split("  ")
        assert hashlib.sha256((salida / nombre).read_bytes()).hexdigest() == suma


def test_no_modifica_el_warehouse(warehouse, tmp_path):
    antes = warehouse.read_bytes()
    exportar(warehouse, tmp_path / "release")
    assert warehouse.read_bytes() == antes


def test_vuelve_a_generar_desde_cero(warehouse, tmp_path):
    salida = tmp_path / "release"
    salida.mkdir()
    (salida / "resto_de_otra_ejecucion.parquet").write_text("viejo")
    exportar(warehouse, salida)
    assert not (salida / "resto_de_otra_ejecucion.parquet").exists()


def test_sin_tablas_en_gold_falla(tmp_path):
    ruta = tmp_path / "vacio.duckdb"
    duckdb.connect(str(ruta)).close()
    with pytest.raises(ValueError, match="gold"):
        exportar(ruta, tmp_path / "release")


def test_solo_borra_y_suma_los_ficheros_que_genera(warehouse, tmp_path):
    # Si la carpeta de salida apunta por error a otra con más cosas, no se borran ni entran en las sumas.
    salida = tmp_path / "release"
    salida.mkdir()
    (salida / "notas.txt").write_text("de otra persona", encoding="utf-8")
    (salida / "subcarpeta").mkdir()

    exportar(warehouse, salida)

    assert (salida / "notas.txt").read_text(encoding="utf-8") == "de otra persona"
    assert (salida / "subcarpeta").is_dir()
    assert "notas.txt" not in (salida / "SHA256SUMS").read_text(encoding="utf-8")
