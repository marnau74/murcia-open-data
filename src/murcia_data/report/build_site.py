"""Genera la web estática del informe (site/index.html) a partir del modelo
estrella en data/processed/. La publica GitHub Pages desde el workflow.

La página es una plantilla HTML con los datos incrustados como JSON: no hay
servidor ni base de datos, y cualquier cifra que aparece en ella sale de
murcia_data/report/indicadores.py.

Uso: python -m murcia_data.report.build_site
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from murcia_data.report.indicadores import (
    anios_completos,
    efecto_no_desglosado,
    indice_anual,
    modelo_plano,
    perfil_estacional,
    perfil_zonas,
    serie_mensual,
)

PROCESSED = Path("data/processed")
PLANTILLA = Path(__file__).with_name("plantilla.html")
SALIDA = Path("site")
MARCADOR = "/*__DATOS__*/null"


def _registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts serializable (fechas ISO, NaN -> null)."""
    df = df.copy()
    for col in df.select_dtypes("datetime").columns:
        df[col] = df[col].dt.strftime("%Y-%m")
    return json.loads(df.to_json(orient="records", double_precision=4))


def construir_datos() -> dict:
    fact = pd.read_parquet(PROCESSED / "fact_ocupacion.parquet")
    dim_destino = pd.read_parquet(PROCESSED / "dim_destino.parquet")
    dim_fecha = pd.read_parquet(PROCESSED / "dim_fecha.parquet")

    plano = modelo_plano(fact, dim_destino, dim_fecha)
    completos = anios_completos(dim_fecha)
    serie = serie_mensual(plano)
    sin_publicar = serie.loc[serie["pernoctaciones"].isna(), "fecha"].drop_duplicates()

    return {
        "generado": date.today().isoformat(),
        "primer_mes": plano["fecha"].min().strftime("%Y-%m"),
        "ultimo_mes": plano["fecha"].max().strftime("%Y-%m"),
        "anios_completos": completos,
        "meses_sin_publicar": [f.strftime("%Y-%m") for f in sin_publicar],
        "perfil_estacional": _registros(perfil_estacional(plano, completos)),
        "serie_mensual": _registros(serie),
        "indice_anual": _registros(indice_anual(plano, completos)),
        "perfil_zonas": _registros(perfil_zonas(plano, completos)),
        "no_desglosado": efecto_no_desglosado(plano, completos),
    }


def main() -> None:
    datos = construir_datos()
    html = PLANTILLA.read_text(encoding="utf-8")
    assert MARCADOR in html, "La plantilla no tiene el marcador de datos"
    html = html.replace(MARCADOR, json.dumps(datos, ensure_ascii=False))

    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "index.html").write_text(html, encoding="utf-8")
    print(f"Web generada en {SALIDA / 'index.html'} (datos hasta {datos['ultimo_mes']}).")


if __name__ == "__main__":
    main()
