"""Capa bronze: carga la capa raw en DuckDB, tipada y con columnas de auditoría.

Reglas de esta capa (ver docs/adr/0003-arquitectura-por-capas.md):
  - Una tabla por fuente, con los datos tal cual los publica la fuente: sin filtrar
    territorios, sin traducir códigos y sin corregir nada. Solo se tipan las columnas,
    se pasan los nombres a snake_case y se quitan las filas vacías de formato.
  - Cada fila lleva `_fichero_origen` y `_ingestado_en` para saber de dónde sale.
  - Cada carga reemplaza la tabla entera (las fuentes se descargan completas en cada
    ejecución) y deja constancia en `bronze._cargas`.

Uso: python -m murcia_data.bronze
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from murcia_data.ingest.murciaturistica_client import parsear_tabla

WAREHOUSE = Path("data/warehouse.duckdb")
RAW = Path("data/raw")

# Esquema de las respuestas de DATOS_SERIE del INE. Declararlo evita depender de la
# inferencia de DuckDB (un fichero sin notas no debe cambiar el tipo de la columna).
ESQUEMA_INE = {
    "COD": "VARCHAR",
    "Nombre": "VARCHAR",
    "Data": (
        "STRUCT(FK_TipoDato BIGINT, FK_Periodo BIGINT, Anyo BIGINT, Valor DOUBLE, "
        "Secreto BOOLEAN, Notas STRUCT(texto VARCHAR)[])[]"
    ),
}
PATRON_INGESTA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATRON_MT = re.compile(r"^destinos_(\d{4})-(\d{2})\.html$")


def conectar(ruta: Path | str = WAREHOUSE) -> duckdb.DuckDBPyConnection:
    """Abre el warehouse y se asegura de que existen el esquema y el registro de cargas."""
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta))
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bronze._cargas (
            tabla VARCHAR NOT NULL,
            filas BIGINT NOT NULL,
            origen VARCHAR NOT NULL,
            cargado_en TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    return con


def ultima_ingesta(raw_ine: Path) -> Path:
    """Carpeta de la ingesta más reciente del INE (data/raw/ine/AAAA-MM-DD)."""
    carpetas = sorted(p for p in raw_ine.iterdir() if p.is_dir() and PATRON_INGESTA.match(p.name))
    if not carpetas:
        raise FileNotFoundError(f"No hay ninguna ingesta del INE en {raw_ine}")
    return carpetas[-1]


def _registrar(con: duckdb.DuckDBPyConnection, tabla: str, origen: str) -> int:
    filas = con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
    if filas == 0:
        raise ValueError(f"La carga de {tabla} desde {origen} no ha producido filas")
    con.execute("INSERT INTO bronze._cargas (tabla, filas, origen) VALUES (?, ?, ?)", [tabla, filas, origen])
    return filas


def cargar_ine(con: duckdb.DuckDBPyConnection, raw: Path = RAW) -> int:
    """bronze.ine_series: una fila por serie y periodo de la última ingesta del INE."""
    carpeta = ultima_ingesta(raw / "ine")
    origen = f"ine/{carpeta.name}"
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.ine_series AS
        SELECT
            s.COD AS codigo,
            s.Nombre AS nombre_serie,
            d.Anyo::SMALLINT AS anio,
            d.FK_Periodo::SMALLINT AS periodo,
            d.FK_TipoDato::SMALLINT AS fk_tipo_dato,
            d.Valor AS valor,
            coalesce(d.Secreto, false) AS secreto,
            array_to_string(list_transform(d.Notas, n -> n.texto), ' | ') AS notas,
            $origen || '/' || parse_filename(s.filename) AS _fichero_origen,
            $fecha::DATE AS _ingestado_en
        FROM read_json($patron, columns = $esquema, filename = true, format = 'auto') AS s,
             UNNEST(s.Data) AS t(d)
        ORDER BY codigo, anio, periodo
        """,
        {
            "patron": (carpeta / "*.json").as_posix(),
            "esquema": ESQUEMA_INE,
            "origen": origen,
            "fecha": carpeta.name,
        },
    )
    return _registrar(con, "bronze.ine_series", origen)


def cargar_murciaturistica(con: duckdb.DuckDBPyConnection, raw: Path = RAW) -> int:
    """bronze.murciaturistica_destinos: una fila por destino o subtotal y mes, tal cual
    la tabla publicada (se quitan solo las filas en blanco que separan los bloques).

    La caché de murciaturistica no guarda fecha de ingesta: se usa la fecha de
    modificación del fichero, que es la de su descarga.
    """
    carpeta = raw / "murciaturistica"
    tablas = []
    for fichero in sorted(carpeta.glob("destinos_*.html")):
        coincidencia = PATRON_MT.match(fichero.name)
        if not coincidencia:
            continue
        anio, mes = int(coincidencia[1]), int(coincidencia[2])
        tabla = parsear_tabla(fichero.read_bytes(), anio, mes)
        tabla = tabla[tabla["destino"].notna()]
        tabla["_fichero_origen"] = f"murciaturistica/{fichero.name}"
        tabla["_ingestado_en"] = date.fromtimestamp(fichero.stat().st_mtime)
        tablas.append(tabla)
    if not tablas:
        raise FileNotFoundError(f"No hay ficheros de murciaturistica en {carpeta}")
    crudo = pd.concat(tablas, ignore_index=True)  # noqa: F841 (lo lee DuckDB por nombre)
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze.murciaturistica_destinos AS
        SELECT
            anio::SMALLINT AS anio,
            mes::SMALLINT AS mes,
            destino::VARCHAR AS destino,
            viajeros_total::BIGINT AS viajeros_total,
            viajeros_residentes::BIGINT AS viajeros_residentes,
            viajeros_no_residentes::BIGINT AS viajeros_no_residentes,
            pernoctaciones_total::BIGINT AS pernoctaciones_total,
            pernoctaciones_residentes::BIGINT AS pernoctaciones_residentes,
            pernoctaciones_no_residentes::BIGINT AS pernoctaciones_no_residentes,
            _fichero_origen::VARCHAR AS _fichero_origen,
            _ingestado_en::DATE AS _ingestado_en
        FROM crudo
        ORDER BY anio, mes, _fichero_origen
        """
    )
    return _registrar(con, "bronze.murciaturistica_destinos", "murciaturistica")


def main() -> None:
    with conectar() as con:
        filas_ine = cargar_ine(con)
        filas_mt = cargar_murciaturistica(con)
    print(f"bronze.ine_series: {filas_ine} filas · bronze.murciaturistica_destinos: {filas_mt} filas")


if __name__ == "__main__":
    main()
