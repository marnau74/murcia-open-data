"""Construcción del modelo estrella a partir de los datos crudos de
murciaturistica.es.

Modelo:
  fact_ocupacion(destino_id, fecha_id, viajeros_residentes, viajeros_no_residentes,
                 pernoctaciones_residentes, pernoctaciones_no_residentes)
  dim_destino(destino_id, nombre, zona)   # zona: ciudad / costa / interior
  dim_fecha(fecha_id, fecha, anio, mes, trimestre, nombre_mes)

Los 11 destinos y su zona son la clasificación oficial que usa el propio
Instituto de Turismo de la Región de Murcia (turismoregiondemurcia.es,
página "Destinos y localidades"), no una clasificación inventada para este
proyecto.

A esos 11 se les suma un destino "(no desglosado)" por zona. Motivo: cuando
el grado de respuesta de las encuestas es bajo, la fuente publica 0 en los
destinos individuales pero mantiene el subtotal real de la zona (secreto
estadístico). Quedándonos solo con los destinos hoja perdíamos 962.644
pernoctaciones de costa en 45 meses —sobre todo de invierno—, lo que
exageraba la estacionalidad de la costa (ratio agosto/enero de 9,4 en vez
del 7,5 real en los años completos 2015-2024). El miembro residual recoge esa diferencia, de modo que sumar
todos los destinos de una zona reproduce siempre el total publicado.

Este módulo trabaja sobre DataFrames de pandas. Las funciones son puras
(entra DataFrame crudo, sale DataFrame de dimensión/hechos) para que cada
una tenga su test en tests/.
"""

from __future__ import annotations

import pandas as pd

ZONA_POR_DESTINO = {
    "Murcia Ciudad": "ciudad",
    "Cartagena": "ciudad",
    "Lorca / Puerto Lumbreras": "ciudad",
    "La Manga": "costa",
    "Resto Mar Menor": "costa",
    "Mazarrón": "costa",
    "Águilas": "costa",
    "Noroeste": "interior",
    "V.Ricote / Balnearios": "interior",
    "Centro": "interior",
    "Altiplano / Este": "interior",
}

# Filas de la tabla cruda que traen el total ya agregado de cada zona.
TOTAL_POR_ZONA = {
    "Total Ciudad": "ciudad",
    "Total Costa": "costa",
    "Total Interior": "interior",
}

# Destino sintético que recoge lo que la fuente no desglosa en cada zona.
NO_DESGLOSADO = {zona: f"{zona.capitalize()} (no desglosado)" for zona in TOTAL_POR_ZONA.values()}

MEDIDAS = [
    "viajeros_residentes",
    "viajeros_no_residentes",
    "pernoctaciones_residentes",
    "pernoctaciones_no_residentes",
]

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def descartar_meses_sin_publicar(crudo: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """Quita los meses que la fuente no ha publicado.

    Para esos meses el portal no devuelve un error sino la tabla completa
    con todas las celdas a 0, totales incluidos. Pasa en marzo-junio y
    diciembre de 2020 (COVID) y en todo mes posterior al último publicado.
    Guardarlos como 0 los haría pasar por meses con cero turistas y
    falsearía cualquier media, así que no entran en la tabla de hechos.

    Devuelve el crudo filtrado y la lista de fecha_id (AAAAMM) descartados.
    """
    suma_mes = crudo.groupby(["anio", "mes"])[MEDIDAS].sum().sum(axis=1)
    vacios = suma_mes[suma_mes == 0].index
    descartados = sorted(anio * 100 + mes for anio, mes in vacios)
    claves = pd.MultiIndex.from_frame(crudo[["anio", "mes"]])
    return crudo[~claves.isin(vacios)].reset_index(drop=True), descartados


def construir_dim_fecha(fechas: pd.Series) -> pd.DataFrame:
    """Genera la dimensión fecha a partir de una serie de fechas (mensuales)."""
    fechas = pd.to_datetime(fechas.dropna().unique())
    df = pd.DataFrame({"fecha": sorted(fechas)})
    df["fecha_id"] = df["fecha"].dt.strftime("%Y%m").astype(int)
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["trimestre"] = df["fecha"].dt.quarter
    df["nombre_mes"] = df["mes"].map(MESES_ES)
    return df[["fecha_id", "fecha", "anio", "mes", "trimestre", "nombre_mes"]]


def construir_dim_destino() -> pd.DataFrame:
    """Genera la dimensión destino con la clasificación oficial ciudad/costa/interior,
    más un miembro "(no desglosado)" por zona (ver docstring del módulo)."""
    zonas = dict(ZONA_POR_DESTINO)
    zonas.update({nombre: zona for zona, nombre in NO_DESGLOSADO.items()})
    df = pd.DataFrame({"nombre": list(zonas)})
    df["destino_id"] = range(1, len(df) + 1)
    df["zona"] = df["nombre"].map(zonas)
    df["desglosado"] = ~df["nombre"].isin(NO_DESGLOSADO.values())
    return df[["destino_id", "nombre", "zona", "desglosado"]]


def _residuales_por_zona(crudo: pd.DataFrame, hojas: pd.DataFrame) -> pd.DataFrame:
    """Diferencia entre el total de zona que publica la fuente y la suma de
    sus destinos hoja. Es lo que la fuente no desglosa (secreto estadístico).

    Devuelve una fila por zona/mes con residual > 0; si la zona cuadra, no
    genera fila. Nunca devuelve residuales negativos: si la suma de hojas
    superase al total publicado sería un error de la fuente, no un hueco.
    """
    totales = crudo[crudo["destino"].isin(TOTAL_POR_ZONA)].copy()
    if totales.empty:
        return pd.DataFrame(columns=["anio", "mes", "zona", *MEDIDAS])
    totales["zona"] = totales["destino"].map(TOTAL_POR_ZONA)

    sumas = hojas.groupby(["anio", "mes", "zona"], as_index=False)[MEDIDAS].sum()
    comp = totales.merge(sumas, on=["anio", "mes", "zona"], how="left", suffixes=("_total", "_hojas"))
    for medida in MEDIDAS:
        comp[medida] = (comp[f"{medida}_total"] - comp[f"{medida}_hojas"].fillna(0)).clip(lower=0)

    residuales = comp[["anio", "mes", "zona", *MEDIDAS]]
    return residuales[residuales[MEDIDAS].sum(axis=1) > 0]


def construir_fact_ocupacion(crudo: pd.DataFrame, dim_destino: pd.DataFrame) -> pd.DataFrame:
    """A partir de la tabla cruda mensual de murciaturistica_client (que
    incluye subtotales de zona y filas en blanco), arma la tabla de hechos
    al grano destino x mes.

    Además de los destinos hoja, añade el residual "(no desglosado)" de cada
    zona para no perder las pernoctaciones que la fuente agrega pero no
    desglosa (ver docstring del módulo).

    Las columnas "_total" del crudo no se guardan: son la suma de
    residentes + no residentes y se pueden recalcular en el consumo.
    """
    hojas = crudo[crudo["destino"].isin(ZONA_POR_DESTINO)].copy()
    hojas["zona"] = hojas["destino"].map(ZONA_POR_DESTINO)

    residuales = _residuales_por_zona(crudo, hojas)
    residuales = residuales.assign(destino=residuales["zona"].map(NO_DESGLOSADO))

    filas = pd.concat([hojas, residuales], ignore_index=True)
    filas = filas.merge(dim_destino[["destino_id", "nombre"]], left_on="destino", right_on="nombre")
    filas["fecha_id"] = filas["anio"] * 100 + filas["mes"]
    filas = filas.sort_values(["fecha_id", "destino_id"])
    return filas[["destino_id", "fecha_id", *MEDIDAS]].reset_index(drop=True)


if __name__ == "__main__":
    # Demo mínima con datos de juguete para comprobar que el módulo corre.
    demo_fechas = pd.to_datetime(["2025-07-01", "2025-08-01"])
    print(construir_dim_fecha(pd.Series(demo_fechas)))
    print(construir_dim_destino())
