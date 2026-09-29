"""Indicadores que se publican en la web, calculados a partir del modelo
estrella. Funciones puras: entra el modelo, sale un DataFrame pequeño listo
para dibujar. Ninguna cifra del informe se escribe a mano.

Criterio común: las comparaciones entre meses se hacen solo con años
completos (los 12 meses publicados). 2020 tiene cinco meses sin publicar y
metido en una media arrastraría el perfil estacional hacia julio-noviembre.
"""

from __future__ import annotations

import pandas as pd

ZONAS = ["costa", "ciudad", "interior"]


def modelo_plano(fact: pd.DataFrame, dim_destino: pd.DataFrame, dim_fecha: pd.DataFrame) -> pd.DataFrame:
    """Une hechos y dimensiones y añade los totales (residentes + no residentes)."""
    plano = fact.merge(dim_destino, on="destino_id").merge(dim_fecha, on="fecha_id")
    plano["pernoctaciones"] = plano["pernoctaciones_residentes"] + plano["pernoctaciones_no_residentes"]
    plano["viajeros"] = plano["viajeros_residentes"] + plano["viajeros_no_residentes"]
    return plano


def anios_completos(dim_fecha: pd.DataFrame) -> list[int]:
    """Años con los 12 meses publicados."""
    meses = dim_fecha.groupby("anio")["mes"].nunique()
    return sorted(int(a) for a in meses[meses == 12].index)


def perfil_estacional(plano: pd.DataFrame, anios: list[int]) -> pd.DataFrame:
    """Porcentaje de las pernoctaciones anuales de cada zona que cae en cada
    mes, sumando los años indicados. Cada zona suma 100."""
    datos = plano[plano["anio"].isin(anios)]
    por_mes = datos.groupby(["zona", "mes"], as_index=False)["pernoctaciones"].sum()
    por_mes["pct"] = por_mes["pernoctaciones"] / por_mes.groupby("zona")["pernoctaciones"].transform("sum") * 100
    return por_mes[["zona", "mes", "pct"]]


def serie_mensual(plano: pd.DataFrame) -> pd.DataFrame:
    """Pernoctaciones por zona y mes, con los meses sin publicar como nulos
    (no como 0) para que el gráfico muestre el hueco."""
    serie = plano.groupby(["zona", "fecha"])["pernoctaciones"].sum()
    meses = pd.date_range(plano["fecha"].min(), plano["fecha"].max(), freq="MS")
    completo = pd.MultiIndex.from_product([ZONAS, meses], names=["zona", "fecha"])
    return serie.reindex(completo).reset_index()


def indice_anual(plano: pd.DataFrame, anios: list[int], base: int = 2019) -> pd.DataFrame:
    """Pernoctaciones anuales de cada zona con base 100 en el año `base`."""
    anual = plano[plano["anio"].isin(anios)].groupby(["zona", "anio"], as_index=False)["pernoctaciones"].sum()
    referencia = anual[anual["anio"] == base].set_index("zona")["pernoctaciones"]
    anual["indice"] = anual["pernoctaciones"] / anual["zona"].map(referencia) * 100
    return anual[["zona", "anio", "pernoctaciones", "indice"]]


def _ratio_agosto_enero(datos: pd.DataFrame) -> float:
    por_mes = datos.groupby("mes")["pernoctaciones"].sum()
    return float(por_mes[8] / por_mes[1])


def perfil_zonas(plano: pd.DataFrame, anios: list[int]) -> pd.DataFrame:
    """Una fila por zona con los rasgos que la definen."""
    datos = plano[plano["anio"].isin(anios)]
    filas = []
    for zona in ZONAS:
        z = datos[datos["zona"] == zona]
        filas.append(
            {
                "zona": zona,
                "ratio_agosto_enero": _ratio_agosto_enero(z),
                "estancia_media": z["pernoctaciones"].sum() / z["viajeros"].sum(),
                "pct_no_residentes": z["pernoctaciones_no_residentes"].sum() / z["pernoctaciones"].sum() * 100,
            }
        )
    return pd.DataFrame(filas)


def efecto_no_desglosado(plano: pd.DataFrame, anios: list[int]) -> dict:
    """Cuánto cambia la estacionalidad de la costa si se ignoran las
    pernoctaciones que la fuente publica en el total de zona pero no
    desglosa por destino (secreto estadístico)."""
    costa = plano[plano["zona"] == "costa"]
    residual = costa[~costa["desglosado"]]
    completos = costa[costa["anio"].isin(anios)]
    return {
        "pernoctaciones_no_desglosadas": int(residual["pernoctaciones"].sum()),
        "meses_afectados": int(residual["fecha_id"].nunique()),
        "pct_del_total": float(residual["pernoctaciones"].sum() / plano["pernoctaciones"].sum() * 100),
        "ratio_con_correccion": _ratio_agosto_enero(completos),
        "ratio_sin_correccion": _ratio_agosto_enero(completos[completos["desglosado"]]),
    }
