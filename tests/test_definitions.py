"""Tests de la orquestación con Dagster: la forma del grafo y los assets de bronze
materializados con los fixtures (sin red)."""

import csv
import json
import shutil
from pathlib import Path

import dagster as dg
import pytest

from murcia_data.definitions import (
    Rutas,
    bronze_ine_series,
    bronze_murciaturistica_destinos,
    defs,
    ejecucion_mensual,
    ine_catalogo_completo,
    ine_datos_recientes,
)

FIXTURES = Path(__file__).parent / "fixtures"
GRAFO = defs.get_repository_def().asset_graph


def _clave(texto: str) -> dg.AssetKey:
    return dg.AssetKey.from_user_string(texto)


# --- Forma del grafo ---------------------------------------------------------------


def test_el_linaje_va_de_la_ingesta_al_mart():
    assert GRAFO.get(_clave("bronze/ine_series")).parent_keys == {_clave("raw_ine")}
    assert GRAFO.get(_clave("silver/stg_ine__series")).parent_keys == {_clave("bronze/ine_series")}
    assert _clave("silver/int_ine__observaciones") in GRAFO.get(_clave("gold/fct_demanda_mensual")).parent_keys


def test_los_assets_se_agrupan_por_capa():
    grupos = {GRAFO.get(clave).group_name for clave in GRAFO.get_all_asset_keys()}
    assert grupos == {"raw", "bronze", "silver", "gold", "referencia"}
    assert GRAFO.get(_clave("gold/dim_territorio")).group_name == "gold"
    assert GRAFO.get(_clave("ref/series_ine")).group_name == "referencia"


def test_los_tests_de_dbt_son_comprobaciones_de_dagster():
    # Los tests de dbt sobre un solo modelo se registran como comprobaciones de su asset.
    # Los que cruzan varios (p. ej. el cuadre con el seed de excepciones) no tienen un
    # único asset al que colgarse, pero se ejecutan igual dentro de `dbt build` y, si
    # fallan, el paso falla.
    comprobaciones = {clave.name for clave in GRAFO.asset_check_keys}
    assert "assert_ine_reparto_residencia_similar" in comprobaciones
    assert "unique_combination_fct_demanda_mensual_fecha_id__territorio_id__tipo_alojamiento_id__residencia_id" in (
        comprobaciones
    )
    assert "ine_catalogo_completo" in comprobaciones


def test_ejecucion_mensual_el_dia_3_en_hora_de_madrid():
    assert ejecucion_mensual.cron_schedule == "0 7 3 * *"
    assert ejecucion_mensual.execution_timezone == "Europe/Madrid"


# --- Bronze con fixtures -----------------------------------------------------------


@pytest.fixture
def rutas(tmp_path) -> Rutas:
    """Capa raw con los fixtures y un catálogo con las dos series que hay en ellos."""
    raw = tmp_path / "raw"
    ine = raw / "ine" / "2026-09-29"
    ine.mkdir(parents=True)
    for fixture in (FIXTURES / "ine").glob("serie_*.json"):
        shutil.copy(fixture, ine / fixture.name.removeprefix("serie_"))
    shutil.copytree(FIXTURES / "murciaturistica", raw / "murciaturistica")

    catalogo = tmp_path / "series_ine.csv"
    with catalogo.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["codigo", "medida"])
        for fixture in (FIXTURES / "ine").glob("serie_*.json"):
            escritor.writerow([json.loads(fixture.read_text(encoding="utf-8"))["COD"], "pernoctaciones"])

    return Rutas(raw=str(raw), warehouse=str(tmp_path / "warehouse.duckdb"), catalogo_ine=str(catalogo))


def _materializar(rutas: Rutas) -> dg.ExecuteInProcessResult:
    return dg.materialize(
        [bronze_ine_series, bronze_murciaturistica_destinos, ine_catalogo_completo, ine_datos_recientes],
        resources={"rutas": rutas},
        raise_on_error=False,
    )


def test_bronze_se_materializa_con_los_fixtures(rutas):
    resultado = _materializar(rutas)

    assert resultado.success
    filas = {
        evento.asset_key.to_user_string(): evento.step_materialization_data.materialization.metadata["filas"].value
        for evento in resultado.get_asset_materialization_events()
    }
    assert filas == {"bronze/ine_series": 12, "bronze/murciaturistica_destinos": 17}


def test_la_comprobacion_del_catalogo_detecta_series_que_faltan(rutas, tmp_path):
    catalogo = Path(rutas.catalogo_ine)
    catalogo.write_text(catalogo.read_text(encoding="utf-8") + "EOT_INEXISTENTE,viajeros\n", encoding="utf-8")

    resultado = _materializar(rutas)

    evaluaciones = {e.check_name: e for e in resultado.get_asset_check_evaluations()}
    assert not evaluaciones["ine_catalogo_completo"].passed
    assert evaluaciones["ine_catalogo_completo"].metadata["faltan"].value == 1


def test_datos_antiguos_solo_generan_aviso(rutas):
    # Los fixtures acaban en agosto de 2026: con la fecha de hoy pueden estar al día o
    # no, pero la comprobación nunca bloquea (severidad WARN).
    resultado = _materializar(rutas)
    evaluacion = {e.check_name: e for e in resultado.get_asset_check_evaluations()}["ine_datos_recientes"]
    assert evaluacion.severity == dg.AssetCheckSeverity.WARN
