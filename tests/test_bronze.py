"""Tests de la capa bronze: raw -> DuckDB sin red, con respuestas reales recortadas."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from murcia_data.bronze import cargar_ine, cargar_murciaturistica, conectar, ultima_ingesta

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def con():
    with conectar(":memory:") as conexion:
        yield conexion


def _serie() -> dict:
    return json.loads((FIXTURES / "ine" / "serie_EOT1772.json").read_text(encoding="utf-8"))


def _guardar_ingesta(raw: Path, fecha: str, serie: dict) -> None:
    carpeta = raw / "ine" / fecha
    carpeta.mkdir(parents=True)
    (carpeta / f"{serie['COD']}.json").write_text(json.dumps(serie, ensure_ascii=False), encoding="utf-8")


def test_ultima_ingesta_elige_la_carpeta_mas_reciente_e_ignora_otras(tmp_path):
    for nombre in ["2026-08-01", "2026-09-29", "notas", "2026-09-01"]:
        (tmp_path / nombre).mkdir()
    assert ultima_ingesta(tmp_path).name == "2026-09-29"


def test_ultima_ingesta_sin_datos_falla(tmp_path):
    with pytest.raises(FileNotFoundError):
        ultima_ingesta(tmp_path)


def test_cargar_ine_usa_la_ultima_ingesta_y_conserva_secreto_y_notas(con, tmp_path):
    antigua = _serie()
    reciente = _serie()
    reciente["Data"][0].update(Valor=None, Secreto=True)
    reciente["Data"][1].update(Valor=None, Notas=[{"texto": "Dato no disponible por cierre", "Fk_TipoNota": 1}])
    _guardar_ingesta(tmp_path, "2026-09-01", antigua)
    _guardar_ingesta(tmp_path, "2026-09-29", reciente)

    filas = cargar_ine(con, tmp_path)

    assert filas == len(reciente["Data"])
    primero, segundo = con.execute(
        "SELECT valor, secreto, notas, _ingestado_en, _fichero_origen FROM bronze.ine_series "
        "ORDER BY anio, periodo LIMIT 2"
    ).fetchall()
    assert primero[:2] == (None, True)
    assert segundo[:3] == (None, False, "Dato no disponible por cierre")
    assert primero[3] == date(2026, 9, 29)
    assert primero[4] == "ine/2026-09-29/EOT1772.json"


def test_cargar_ine_tipa_las_columnas(con, tmp_path):
    _guardar_ingesta(tmp_path, "2026-09-29", _serie())
    cargar_ine(con, tmp_path)
    tipos = dict(con.execute("SELECT column_name, column_type FROM (DESCRIBE bronze.ine_series)").fetchall())
    assert tipos["anio"] == "SMALLINT"
    assert tipos["valor"] == "DOUBLE"
    assert tipos["secreto"] == "BOOLEAN"
    assert tipos["_ingestado_en"] == "DATE"


def test_cargar_ine_sin_filas_falla(con, tmp_path):
    vacia = _serie()
    vacia["Data"] = []
    _guardar_ingesta(tmp_path, "2026-09-29", vacia)
    with pytest.raises(ValueError, match="no ha producido filas"):
        cargar_ine(con, tmp_path)


def test_cargar_murciaturistica_conserva_la_tabla_publicada(con, tmp_path):
    carpeta = tmp_path / "murciaturistica"
    carpeta.mkdir()
    shutil.copy(FIXTURES / "murciaturistica" / "destinos_2019-07.html", carpeta)

    filas = cargar_murciaturistica(con, tmp_path)

    destinos = [d for (d,) in con.execute("SELECT destino FROM bronze.murciaturistica_destinos").fetchall()]
    assert filas == 17  # 11 destinos + 5 subtotales + total; sin las filas en blanco
    assert "Mazarrón" in destinos and "Águilas" in destinos  # la codificación de la fuente se respeta
    assert "Total Costa" in destinos and "Totales" in destinos
    total = con.execute(
        "SELECT pernoctaciones_no_residentes, _fichero_origen FROM bronze.murciaturistica_destinos "
        "WHERE destino = 'Totales'"
    ).fetchone()
    assert total == (93220, "murciaturistica/destinos_2019-07.html")


def test_cada_carga_queda_registrada(con, tmp_path):
    _guardar_ingesta(tmp_path, "2026-09-29", _serie())
    cargar_ine(con, tmp_path)
    cargar_ine(con, tmp_path)
    cargas = con.execute("SELECT tabla, origen FROM bronze._cargas").fetchall()
    assert cargas == [("bronze.ine_series", "ine/2026-09-29")] * 2
