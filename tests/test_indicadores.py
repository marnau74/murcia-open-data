"""Tests de los indicadores que se publican en la web."""
import pandas as pd
import pytest

from src.report.indicadores import (
    anios_completos,
    efecto_no_desglosado,
    indice_anual,
    modelo_plano,
    perfil_estacional,
    serie_mensual,
)
from src.transform.star_schema import construir_dim_destino, construir_dim_fecha


def _modelo(filas):
    """Construye el modelo plano a partir de filas (anio, mes, destino, pernoctaciones)."""
    dim_destino = construir_dim_destino()
    ids = dict(zip(dim_destino["nombre"], dim_destino["destino_id"]))
    fact = pd.DataFrame(
        [
            {
                "destino_id": ids[destino],
                "fecha_id": anio * 100 + mes,
                "viajeros_residentes": p // 2,
                "viajeros_no_residentes": 0,
                "pernoctaciones_residentes": p,
                "pernoctaciones_no_residentes": 0,
            }
            for anio, mes, destino, p in filas
        ]
    )
    fechas = pd.to_datetime(pd.DataFrame({"year": [f[0] for f in filas], "month": [f[1] for f in filas], "day": 1}))
    dim_fecha = construir_dim_fecha(fechas)
    return modelo_plano(fact, dim_destino, dim_fecha), dim_fecha


@pytest.fixture
def dos_anios():
    """2019 completo en La Manga y Murcia Ciudad; 2020 solo con enero."""
    filas = [(2019, m, "La Manga", 100 * m) for m in range(1, 13)]
    filas += [(2019, m, "Murcia Ciudad", 50) for m in range(1, 13)]
    filas += [(2020, 1, "La Manga", 80), (2020, 1, "Murcia Ciudad", 40)]
    return _modelo(filas)


def test_anios_completos_excluye_anios_con_meses_sin_publicar(dos_anios):
    _, dim_fecha = dos_anios
    assert anios_completos(dim_fecha) == [2019]


def test_perfil_estacional_suma_100_por_zona(dos_anios):
    plano, _ = dos_anios
    perfil = perfil_estacional(plano, [2019])
    assert perfil.groupby("zona")["pct"].sum().round(6).eq(100).all()
    # Murcia Ciudad tiene el mismo valor cada mes: reparto uniforme
    ciudad = perfil[perfil["zona"] == "ciudad"]["pct"]
    assert ciudad.round(6).eq(round(100 / 12, 6)).all()


def test_serie_mensual_deja_nulos_los_meses_sin_publicar(dos_anios):
    plano, _ = dos_anios
    plano = plano[plano["fecha_id"] != 201906]  # un mes sin publicar en medio
    serie = serie_mensual(plano)
    junio = serie[serie["fecha"] == "2019-06-01"]
    assert junio["pernoctaciones"].isna().all()  # hueco, no cero
    assert len(serie) == 3 * 13  # 3 zonas x 13 meses (ene 2019 - ene 2020)


def test_indice_anual_base_100(dos_anios):
    plano, _ = dos_anios
    indice = indice_anual(plano, [2019])
    assert indice["indice"].round(6).eq(100).all()


def test_efecto_no_desglosado_mide_el_sesgo_de_estacionalidad():
    """Si el dato de enero de la costa no está desglosado, ignorarlo infla
    la relación agosto/enero."""
    filas = [(2019, m, "La Manga", 1000) for m in range(1, 13)]
    filas = [f for f in filas if f[1] != 1]
    filas += [(2019, 1, "La Manga", 100), (2019, 1, "Costa (no desglosado)", 400)]
    plano, _ = _modelo(filas)
    efecto = efecto_no_desglosado(plano, [2019])
    assert efecto["ratio_con_correccion"] == pytest.approx(2.0)   # 1000 / 500
    assert efecto["ratio_sin_correccion"] == pytest.approx(10.0)  # 1000 / 100
    assert efecto["pernoctaciones_no_desglosadas"] == 400
    assert efecto["meses_afectados"] == 1
