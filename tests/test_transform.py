"""Tests de las funciones de transformación y de las comprobaciones de calidad."""

import numpy as np
import pandas as pd
import pytest

from murcia_data.quality.checks import (
    cuadra_con_totales_publicados,
    integridad_referencial,
    rango_valido,
    sin_duplicados,
    sin_nulos_en_claves,
)
from murcia_data.transform.star_schema import (
    MEDIDAS,
    construir_dim_destino,
    construir_dim_fecha,
    construir_fact_ocupacion,
    descartar_meses_sin_publicar,
)


def _fila(anio, mes, destino, viajeros_res, viajeros_nores, pernoc_res, pernoc_nores):
    return {
        "anio": anio,
        "mes": mes,
        "destino": destino,
        "viajeros_total": viajeros_res + viajeros_nores,
        "viajeros_residentes": viajeros_res,
        "viajeros_no_residentes": viajeros_nores,
        "pernoctaciones_total": pernoc_res + pernoc_nores,
        "pernoctaciones_residentes": pernoc_res,
        "pernoctaciones_no_residentes": pernoc_nores,
    }


@pytest.fixture
def datos_crudos():
    # Tal cual los devuelve MurciaturisticaClient: incluye subtotales de
    # zona ("Total Ciudad") y filas en blanco entre bloques.
    filas = [
        _fila(2019, 7, "Murcia Ciudad", 27592, 10046, 41391, 21557),
        _fila(2019, 7, "Cartagena", 11088, 3975, 22798, 7125),
        _fila(2019, 7, "Total Ciudad", 38680, 14021, 64189, 28682),
        {**{k: np.nan for k in _fila(2019, 7, "x", 0, 0, 0, 0)}, "anio": 2019, "mes": 7, "destino": np.nan},
        _fila(2019, 7, "La Manga", 21262, 4788, 90856, 26407),
        _fila(2019, 8, "Murcia Ciudad", 25000, 12000, 39000, 24000),
        _fila(2019, 8, "Cartagena", 10000, 4200, 21000, 7600),
        _fila(2019, 8, "Total Ciudad", 35000, 16200, 60000, 31600),
        {**{k: np.nan for k in _fila(2019, 8, "x", 0, 0, 0, 0)}, "anio": 2019, "mes": 8, "destino": np.nan},
        _fila(2019, 8, "La Manga", 19000, 5200, 88000, 27000),
    ]
    return pd.DataFrame(filas)


def test_dim_fecha_una_fila_por_mes(datos_crudos):
    fechas = pd.to_datetime(dict(year=datos_crudos["anio"], month=datos_crudos["mes"], day=1))
    dim = construir_dim_fecha(fechas)
    assert len(dim) == 2  # julio y agosto
    assert set(dim["nombre_mes"]) == {"julio", "agosto"}
    assert dim["trimestre"].tolist() == [3, 3]


def test_dim_destino_clasifica_ciudad_costa_interior():
    dim = construir_dim_destino()
    zonas = dict(zip(dim["nombre"], dim["zona"], strict=True))
    assert zonas["Murcia Ciudad"] == "ciudad"
    assert zonas["Cartagena"] == "ciudad"  # clasificación oficial: no es "costa"
    assert zonas["La Manga"] == "costa"
    assert zonas["Noroeste"] == "interior"


def test_dim_destino_incluye_no_desglosado_por_zona():
    dim = construir_dim_destino()
    residuales = dim[~dim["desglosado"]]
    assert len(residuales) == 3
    assert set(residuales["zona"]) == {"ciudad", "costa", "interior"}
    assert (dim["desglosado"].sum()) == 11  # los 11 destinos oficiales


def test_dim_destino_id_unico():
    dim = construir_dim_destino()
    sin_duplicados(dim, ["destino_id"])
    sin_nulos_en_claves(dim, ["destino_id", "nombre"])


def test_fact_ocupacion_descarta_subtotales_y_filas_en_blanco(datos_crudos):
    dim_destino = construir_dim_destino()
    fact = construir_fact_ocupacion(datos_crudos, dim_destino)
    # Solo quedan las filas de destino-hoja: Murcia Ciudad, Cartagena, La Manga x 2 meses
    assert len(fact) == 6
    assert set(fact.columns) == {
        "destino_id",
        "fecha_id",
        "viajeros_residentes",
        "viajeros_no_residentes",
        "pernoctaciones_residentes",
        "pernoctaciones_no_residentes",
    }


def test_fact_ocupacion_fecha_id_correcto(datos_crudos):
    dim_destino = construir_dim_destino()
    fact = construir_fact_ocupacion(datos_crudos, dim_destino)
    assert set(fact["fecha_id"]) == {201907, 201908}


def test_fact_ocupacion_integridad_referencial(datos_crudos):
    dim_destino = construir_dim_destino()
    fechas = pd.to_datetime(dict(year=datos_crudos["anio"], month=datos_crudos["mes"], day=1))
    dim_fecha = construir_dim_fecha(fechas)
    fact = construir_fact_ocupacion(datos_crudos, dim_destino)
    integridad_referencial(fact, "destino_id", dim_destino, "destino_id")
    integridad_referencial(fact, "fecha_id", dim_fecha, "fecha_id")


def test_fact_ocupacion_recupera_lo_no_desglosado():
    """Caso real (diciembre 2019): la fuente publica 0 en los destinos de
    costa por secreto estadístico, pero el total de zona sí trae el dato.
    Sin el residual perderíamos esas pernoctaciones."""
    crudo = pd.DataFrame(
        [
            _fila(2019, 12, "La Manga", 0, 0, 0, 0),
            _fila(2019, 12, "Resto Mar Menor", 0, 0, 0, 0),
            _fila(2019, 12, "Mazarrón", 0, 0, 0, 0),
            _fila(2019, 12, "Águilas", 0, 0, 0, 0),
            _fila(2019, 12, "Total Costa", 5000, 1200, 24000, 8178),
        ]
    )
    dim_destino = construir_dim_destino()
    fact = construir_fact_ocupacion(crudo, dim_destino)

    con_zona = fact.merge(dim_destino, on="destino_id")
    costa = con_zona[con_zona["zona"] == "costa"]
    # Sumar la zona reproduce el total publicado, pese a los ceros de la fuente
    assert costa["pernoctaciones_residentes"].sum() == 24000
    assert costa["pernoctaciones_no_residentes"].sum() == 8178
    assert costa["viajeros_residentes"].sum() == 5000
    # y queda marcado como no desglosado, no atribuido a un destino concreto
    assert costa.loc[costa["pernoctaciones_residentes"] > 0, "desglosado"].tolist() == [False]


def test_fact_ocupacion_sin_residual_cuando_la_zona_cuadra():
    """Si los destinos hoja ya suman el total publicado, no se inventa
    ninguna fila residual."""
    crudo = pd.DataFrame(
        [
            _fila(2019, 7, "Murcia Ciudad", 100, 10, 200, 20),
            _fila(2019, 7, "Cartagena", 50, 5, 80, 8),
            _fila(2019, 7, "Lorca / Puerto Lumbreras", 20, 2, 30, 3),
            _fila(2019, 7, "Total Ciudad", 170, 17, 310, 31),
        ]
    )
    dim_destino = construir_dim_destino()
    fact = construir_fact_ocupacion(crudo, dim_destino)
    con_zona = fact.merge(dim_destino, on="destino_id")
    assert con_zona["desglosado"].all()
    assert len(fact) == 3


def test_integridad_referencial_detecta_huerfanas():
    hechos = pd.DataFrame({"destino_id": [1, 2, 99]})
    dim = pd.DataFrame({"destino_id": [1, 2]})
    with pytest.raises(AssertionError):
        integridad_referencial(hechos, "destino_id", dim, "destino_id")


def test_cuadra_con_totales_publicados_detecta_zona_incompleta():
    """Si la tabla de hechos pierde el dato suprimido de una zona, la
    validación tiene que cazarlo (es el bug que motivó el residual)."""
    dim_destino = construir_dim_destino()
    id_la_manga = int(dim_destino.loc[dim_destino["nombre"] == "La Manga", "destino_id"].iloc[0])
    hechos = pd.DataFrame([{"destino_id": id_la_manga, "fecha_id": 201912, **{m: 0 for m in MEDIDAS}}])
    publicados = pd.DataFrame([{"fecha_id": 201912, "zona": "costa", **{m: 1000 for m in MEDIDAS}}])
    with pytest.raises(AssertionError, match="no cuadran"):
        cuadra_con_totales_publicados(hechos, dim_destino, publicados, MEDIDAS)


def test_rango_valido_detecta_negativos():
    df = pd.DataFrame({"pernoctaciones_residentes": [10, -5, 3]})
    with pytest.raises(AssertionError):
        rango_valido(df, "pernoctaciones_residentes")


def test_descartar_meses_sin_publicar():
    """La fuente devuelve la tabla entera a 0 para los meses que no publica
    (COVID, meses futuros). No deben entrar como meses con cero turistas."""
    crudo = pd.DataFrame(
        [
            _fila(2020, 3, "Murcia Ciudad", 0, 0, 0, 0),
            _fila(2020, 3, "Total Ciudad", 0, 0, 0, 0),
            _fila(2020, 7, "Murcia Ciudad", 100, 10, 200, 20),
            _fila(2020, 7, "Total Ciudad", 100, 10, 200, 20),
        ]
    )
    filtrado, descartados = descartar_meses_sin_publicar(crudo)
    assert descartados == [202003]
    assert set(filtrado["mes"]) == {7}
    assert len(filtrado) == 2


def test_descartar_meses_sin_publicar_respeta_ceros_parciales():
    """Un mes con destinos a 0 por secreto estadístico pero con total de zona
    publicado sí está publicado: no se descarta."""
    crudo = pd.DataFrame(
        [
            _fila(2019, 12, "La Manga", 0, 0, 0, 0),
            _fila(2019, 12, "Total Costa", 5000, 1200, 24000, 8178),
        ]
    )
    filtrado, descartados = descartar_meses_sin_publicar(crudo)
    assert descartados == []
    assert len(filtrado) == 2
