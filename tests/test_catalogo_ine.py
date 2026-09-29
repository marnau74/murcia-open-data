"""Tests del catálogo de series del INE: la clasificación con metadatos reales y la
validez del seed versionado en dbt/seeds/series_ine.csv."""

import csv
import json
from pathlib import Path

import pytest

from murcia_data.ingest.catalogo_ine import (
    COLUMNAS,
    MEDIDAS,
    MEDIDAS_PRECIOS,
    TABLAS,
    MetadatoDesconocido,
    Tabla,
    clasificar_serie,
    construir_catalogo,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ine"
SEED = Path(__file__).parents[1] / "dbt" / "seeds" / "series_ine.csv"
HOTEL_DEMANDA = Tabla(2074, "EOH", "hotel", "demanda")
IPH = Tabla(12156, "IPH", "hotel", "precios")


def _fixture(nombre: str) -> list[dict]:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def test_clasifica_las_series_de_la_region_por_residencia():
    filas = [clasificar_serie(s, HOTEL_DEMANDA) for s in _fixture("metadatos_2074")]
    murcia = [f for f in filas if f is not None]

    assert {f["territorio"] for f in murcia} == {"region-murcia"}
    assert {f["residencia"] for f in murcia} == {"espana", "extranjero"}  # el total se descarta
    assert {f["medida"] for f in murcia} == {"viajeros", "pernoctaciones"}


def test_descarta_otros_territorios():
    andalucia = [s for s in _fixture("metadatos_2074") if "Andaluc" in s["Nombre"]]
    assert andalucia
    assert all(clasificar_serie(s, HOTEL_DEMANDA) is None for s in andalucia)


def test_la_region_repetida_como_comunidad_y_provincia_no_se_duplica():
    catalogo = construir_catalogo({t.id: (_fixture("metadatos_2074") if t.id == 2074 else []) for t in TABLAS})
    # 2 medidas x 2 residencias, aunque la tabla trae Murcia como comunidad y como provincia
    assert len(catalogo) == 4


def test_zona_turistica_costa_calida():
    tabla = Tabla(2039, "EOH", "hotel", "demanda")
    filas = [clasificar_serie(s, tabla) for s in _fixture("metadatos_2039")]
    assert {(f["territorio"], f["nivel_territorio"]) for f in filas} == {("costa-calida", "zona")}


def test_precios_de_la_region_y_de_espana():
    filas = [clasificar_serie(s, IPH) for s in _fixture("metadatos_12156")]
    assert {(f["territorio"], f["medida"]) for f in filas} == {
        ("region-murcia", "indice_precios"),
        ("region-murcia", "variacion_interanual_precios"),
        ("espana", "indice_precios"),
        ("espana", "variacion_interanual_precios"),
    }


def test_el_total_nacional_solo_se_admite_en_precios():
    nacional = next(s for s in _fixture("metadatos_12156") if "Nacional" in s["Nombre"])
    assert clasificar_serie(nacional, HOTEL_DEMANDA) is None


def test_un_concepto_desconocido_hace_fallar_la_generacion():
    serie = json.loads(json.dumps(_fixture("metadatos_2074")[1]))
    for md in serie["MetaData"]:
        if md["T3_Variable"] == "Concepto turístico":
            md["Nombre"] = "Algo nuevo del INE"
    with pytest.raises(MetadatoDesconocido, match="Algo nuevo del INE"):
        clasificar_serie(serie, HOTEL_DEMANDA)


# --- El seed versionado -------------------------------------------------------


@pytest.fixture(scope="module")
def seed() -> list[dict]:
    with SEED.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_seed_tiene_las_columnas_esperadas(seed):
    assert list(seed[0].keys()) == COLUMNAS


def test_seed_codigos_unicos(seed):
    codigos = [f["codigo"] for f in seed]
    assert len(codigos) == len(set(codigos))


def test_seed_sin_combinaciones_repetidas(seed):
    claves = [(f["hecho"], f["tipo_alojamiento"], f["territorio"], f["medida"], f["residencia"]) for f in seed]
    assert len(claves) == len(set(claves))


def test_seed_valores_permitidos(seed):
    medidas = set(MEDIDAS.values()) | set(MEDIDAS_PRECIOS.values())
    for fila in seed:
        assert fila["hecho"] in {"demanda", "oferta", "precios"}
        assert fila["tipo_alojamiento"] in {"hotel", "apartamento", "camping", "rural"}
        assert fila["medida"] in medidas
        # La residencia solo existe en demanda, y en demanda siempre existe
        assert (fila["residencia"] != "") == (fila["hecho"] == "demanda")


def test_seed_cubre_los_cuatro_tipos_de_alojamiento_en_la_region(seed):
    region = [f for f in seed if f["territorio"] == "region-murcia" and f["hecho"] == "demanda"]
    region_demanda = {f["tipo_alojamiento"] for f in region}
    assert region_demanda == {"hotel", "apartamento", "camping", "rural"}
