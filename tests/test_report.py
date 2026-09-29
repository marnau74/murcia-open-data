"""Tests de los indicadores de la web y de su generación, sobre una capa gold sintética."""

import json

import duckdb
import pytest

from murcia_data.report.build_site import MARCADOR, generar
from murcia_data.report.indicadores import (
    _INE_REGION,
    _MT_ZONAS,
    anios_completos,
    calcular,
    cuadre_fuentes,
    perfil_estacional,
    serie_mensual_tipos,
)


@pytest.fixture
def warehouse(tmp_path):
    """2019 completo y 2020 hasta junio. INE: hoteles y campings en la Región (a los
    campings les falta abril de 2020). murciaturistica: un destino de costa y otro de
    ciudad que suman exactamente los hoteles del INE, salvo los viajeros de enero de 2019
    (excepción documentada)."""
    ruta = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(ruta)) as con:
        con.execute("CREATE SCHEMA gold; CREATE SCHEMA ref;")
        con.execute("""
            CREATE TABLE gold.dim_fecha AS
            SELECT strftime(f, '%Y%m')::INT AS fecha_id, f::DATE AS fecha, year(f)::SMALLINT AS anio,
                   month(f)::SMALLINT AS mes
            FROM (SELECT unnest(generate_series(DATE '2019-01-01', DATE '2020-06-01', INTERVAL 1 MONTH)) AS f)
        """)
        con.execute("""
            CREATE TABLE gold.dim_territorio AS SELECT * FROM (VALUES
                ('region-murcia', NULL), ('destino-la-manga', 'zona-costa'), ('destino-murcia-ciudad', 'zona-ciudad')
            ) AS t(territorio_id, padre_id)
        """)
        con.execute("""
            CREATE TABLE gold.fct_demanda_mensual AS
            WITH meses AS (SELECT fecha_id, mes FROM gold.dim_fecha),
            residencias AS (SELECT unnest(['espana', 'extranjero']) AS residencia_id)
            SELECT fecha_id, 'region-murcia' AS territorio_id, 'hotel' AS tipo_alojamiento_id, residencia_id,
                   (40 * mes)::BIGINT AS viajeros, (100 * mes)::BIGINT AS pernoctaciones,
                   fecha_id >= 202006 AS es_provisional, 'INE' AS fuente
            FROM meses, residencias
            UNION ALL
            SELECT fecha_id, 'region-murcia', 'camping', residencia_id, 20, 50, false, 'INE'
            FROM meses, residencias WHERE fecha_id <> 202004
            UNION ALL
            SELECT fecha_id, 'destino-la-manga', 'hotel', residencia_id,
                   (25 * mes + CASE WHEN fecha_id = 201901 THEN 100 ELSE 0 END)::BIGINT, (60 * mes)::BIGINT,
                   false, 'murciaturistica'
            FROM meses, residencias
            UNION ALL
            SELECT fecha_id, 'destino-murcia-ciudad', 'hotel', residencia_id, (15 * mes)::BIGINT, (40 * mes)::BIGINT,
                   false, 'murciaturistica'
            FROM meses, residencias
        """)
        con.execute("""
            CREATE TABLE gold.fct_oferta_mensual AS
            SELECT fecha_id, 'region-murcia' AS territorio_id, 'hotel' AS tipo_alojamiento_id,
                   (1000 + 10 * mes)::BIGINT AS personal_empleado
            FROM gold.dim_fecha
        """)
        con.execute("""
            CREATE TABLE gold.fct_precios_mensual AS
            SELECT fecha_id, t AS territorio_id, 100.0 + mes AS indice_precios, 1.5 AS variacion_interanual
            FROM gold.dim_fecha, (SELECT unnest(['region-murcia', 'espana']) AS t)
        """)
        con.execute("""
            CREATE TABLE ref.excepciones_cuadre AS
            SELECT 201901 AS fecha_id, 'viajeros' AS medida, 'Diferencia de prueba' AS motivo
        """)
    return ruta


@pytest.fixture
def con(warehouse):
    with duckdb.connect(str(warehouse), read_only=True) as conexion:
        yield conexion


def test_anios_completos_excluye_el_anio_con_meses_sin_publicar(con):
    assert anios_completos(con, _INE_REGION) == [2019]
    assert anios_completos(con, _MT_ZONAS) == [2019]


def test_perfil_estacional_suma_100_por_grupo(con):
    perfil = perfil_estacional(con, _INE_REGION, [2019])
    for tipo in ("hotel", "camping"):
        assert sum(f["pct"] for f in perfil if f["grupo"] == tipo) == pytest.approx(100)
    # Los campings reciben lo mismo cada mes: reparto uniforme
    assert all(f["pct"] == pytest.approx(100 / 12) for f in perfil if f["grupo"] == "camping")


def test_serie_deja_hueco_en_el_mes_sin_dato(con):
    serie = {(f["tipo"], f["fecha"]): f for f in serie_mensual_tipos(con)}
    assert serie[("camping", "2020-04")]["pernoctaciones"] is None  # hueco, no 0
    assert serie[("hotel", "2020-04")]["pernoctaciones"] == 800
    assert serie[("hotel", "2020-06")]["provisional"] is True


def test_cuadre_cuenta_los_meses_y_lista_las_excepciones(con):
    cuadre = cuadre_fuentes(con)
    assert cuadre["meses"] == 18
    assert cuadre["meses_pernoctaciones_cuadran"] == 18
    assert cuadre["meses_viajeros_cuadran"] == 17  # enero de 2019 difiere en 200
    assert cuadre["excepciones"] == [{"fecha_id": 201901, "medida": "viajeros", "motivo": "Diferencia de prueba"}]


def test_calcular_devuelve_todas_las_secciones(con):
    datos = calcular(con)
    assert datos["meta"]["ultimo_mes_ine"] == "2020-06"
    assert datos["meta"]["provisional_desde"] == "2020-06"
    assert {z["zona"] for z in datos["perfil_zonas"]} == {"costa", "ciudad"}
    costa = next(z for z in datos["perfil_zonas"] if z["zona"] == "costa")
    assert costa["ratio_agosto_enero"] == pytest.approx(8)  # 60·8 / 60·1
    assert {p["territorio"] for p in datos["precios"]} == {"region-murcia", "espana"}


def test_generar_incrusta_los_datos_en_la_plantilla(warehouse, tmp_path):
    destino = generar(str(warehouse), tmp_path / "site")
    html = destino.read_text(encoding="utf-8")
    assert MARCADOR not in html
    inicio = html.index("const DATOS = ") + len("const DATOS = ")
    datos = json.loads(html[inicio : html.index(";\n", inicio)])
    assert datos["meta"]["anios_completos_ine"] == [2019]
