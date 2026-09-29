"""Comprobaciones de calidad de datos, reutilizables desde el pipeline
y desde los tests. Cada función lanza AssertionError con un mensaje claro
si el dato no cumple, para que falle visible en CI.
"""
from __future__ import annotations

import pandas as pd


def sin_nulos_en_claves(df: pd.DataFrame, claves: list[str]) -> None:
    """Ninguna columna clave puede tener nulos."""
    for col in claves:
        n = df[col].isna().sum()
        assert n == 0, f"La clave '{col}' tiene {n} nulos"


def sin_duplicados(df: pd.DataFrame, claves: list[str]) -> None:
    """La combinación de claves debe ser única (grano de la tabla de hechos)."""
    dups = df.duplicated(subset=claves).sum()
    assert dups == 0, f"Hay {dups} filas duplicadas para las claves {claves}"


def integridad_referencial(hechos: pd.DataFrame, clave: str, dim: pd.DataFrame, clave_dim: str) -> None:
    """Toda clave foránea de la tabla de hechos existe en su dimensión."""
    huerfanas = set(hechos[clave]) - set(dim[clave_dim])
    assert not huerfanas, f"{len(huerfanas)} valores de '{clave}' no están en la dimensión: {list(huerfanas)[:5]}"


def rango_valido(df: pd.DataFrame, col: str, minimo: float = 0) -> None:
    """Las métricas no pueden ser negativas (ni pernoctaciones ni viajeros)."""
    bajo = (df[col] < minimo).sum()
    assert bajo == 0, f"La columna '{col}' tiene {bajo} valores por debajo de {minimo}"


def cuadra_con_totales_publicados(
    hechos: pd.DataFrame,
    dim_destino: pd.DataFrame,
    totales_publicados: pd.DataFrame,
    medidas: list[str],
) -> None:
    """Sumar los destinos de una zona debe reproducir el total que publica la
    fuente para esa zona y mes.

    No es una comprobación redundante: la fuente pone 0 en los destinos
    individuales cuando el grado de respuesta es bajo, pero mantiene el
    subtotal de zona. Sin esta validación, ese hueco pasa desapercibido y
    subestima la zona (ocurrió con la costa: 962.644 pernoctaciones perdidas
    en 45 meses, sobre todo de invierno, que exageraban su estacionalidad).
    """
    sumado = (
        hechos.merge(dim_destino[["destino_id", "zona"]], on="destino_id")
        .groupby(["fecha_id", "zona"])[medidas]
        .sum()
    )
    esperado = totales_publicados.set_index(["fecha_id", "zona"])[medidas]
    descuadre = (sumado - esperado).abs() > 0.5
    n = int(descuadre.sum().sum())
    assert n == 0, (
        f"{n} celdas no cuadran con los totales publicados por zona. "
        f"Ejemplos: {descuadre[descuadre.any(axis=1)].index[:3].tolist()}"
    )
