# 0001 · DuckDB como warehouse

- **Estado:** aceptada
- **Fecha:** 2026-09-29

## Contexto

La v2 integra varias fuentes (INE y murciaturistica) y pasa las transformaciones a SQL
con dbt. Hace falta un motor analítico donde vivan las capas del modelo. El volumen es
pequeño (decenas de miles de filas), el proyecto se ejecuta en local y en GitHub Actions,
y cualquiera debería poder reproducirlo con un `git clone` sin crear cuentas ni levantar
servidores.

## Decisión

Usar **DuckDB** como warehouse: un único fichero `warehouse.duckdb` con un esquema por
capa, transformado con `dbt-duckdb`.

## Alternativas descartadas

- **PostgreSQL:** exige un servidor en local y en la CI, y no aporta nada para una carga
  analítica de este tamaño.
- **Parquet suelto + pandas:** es lo que hacía la v1. No permite SQL versionado con
  tests, contratos ni linaje.
- **Databricks como único destino:** obliga a tener cuenta y conexión para ejecutar
  cualquier cosa. Se usa como segundo destino del mismo proyecto dbt (fase 8), no como
  base.

## Consecuencias

- Todo el proyecto funciona sin red salvo la ingesta, y la CI de los PR corre con
  *fixtures*.
- El fichero de DuckDB se puede publicar como producto de datos en cada *release* y lo
  puede leer directamente la API .NET (DuckDB.NET).
- DuckDB no admite escrituras concurrentes de varios procesos: basta con que el pipeline
  sea el único que escribe.
