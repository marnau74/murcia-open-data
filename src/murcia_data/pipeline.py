"""Punto de entrada del pipeline: ingesta -> transformación -> validación -> guardado.

Fuente: viajeros y pernoctaciones por destino turístico (murciaturistica.es),
ver murcia_data/ingest/murciaturistica_client.py para el porqué de esta fuente y las
particularidades del endpoint.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from murcia_data.ingest.murciaturistica_client import INICIO_SERIE, MurciaturisticaClient, mes_anterior
from murcia_data.quality.checks import (
    cuadra_con_totales_publicados,
    integridad_referencial,
    rango_valido,
    sin_duplicados,
    sin_nulos_en_claves,
)
from murcia_data.transform.star_schema import (
    MEDIDAS,
    TOTAL_POR_ZONA,
    construir_dim_destino,
    construir_dim_fecha,
    construir_fact_ocupacion,
    descartar_meses_sin_publicar,
)

PROCESSED = Path("data/processed")


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    # 1. INGESTA
    cliente = MurciaturisticaClient()
    crudo = cliente.serie(*INICIO_SERIE, *mes_anterior(date.today()))

    # 2. TRANSFORMACIÓN a modelo estrella
    crudo, sin_publicar = descartar_meses_sin_publicar(crudo)
    dim_destino = construir_dim_destino()
    fechas = pd.to_datetime(dict(year=crudo["anio"], month=crudo["mes"], day=1))
    dim_fecha = construir_dim_fecha(fechas)
    fact = construir_fact_ocupacion(crudo, dim_destino)

    # 3. VALIDACIÓN
    sin_nulos_en_claves(fact, ["destino_id", "fecha_id"])
    sin_duplicados(fact, ["destino_id", "fecha_id"])
    integridad_referencial(fact, "destino_id", dim_destino, "destino_id")
    integridad_referencial(fact, "fecha_id", dim_fecha, "fecha_id")
    for columna in MEDIDAS:
        rango_valido(fact, columna)

    publicados = crudo[crudo["destino"].isin(TOTAL_POR_ZONA)].copy()
    publicados["zona"] = publicados["destino"].map(TOTAL_POR_ZONA)
    publicados["fecha_id"] = publicados["anio"] * 100 + publicados["mes"]
    cuadra_con_totales_publicados(fact, dim_destino, publicados, MEDIDAS)

    # 4. GUARDADO en Parquet
    fact.to_parquet(PROCESSED / "fact_ocupacion.parquet", index=False)
    dim_destino.to_parquet(PROCESSED / "dim_destino.parquet", index=False)
    dim_fecha.to_parquet(PROCESSED / "dim_fecha.parquet", index=False)

    print(f"Pipeline OK: {len(fact)} filas de hechos, {len(dim_destino)} destinos, {len(dim_fecha)} meses.")
    print(f"Último mes publicado: {dim_fecha['fecha_id'].max()}. Meses sin publicar descartados: {len(sin_publicar)}.")


if __name__ == "__main__":
    main()
