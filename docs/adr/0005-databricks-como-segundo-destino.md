# 0005 · Databricks como segundo destino del mismo proyecto dbt

- **Estado:** aceptada
- **Fecha:** 2026-09-29

## Contexto

El proyecto funciona entero con DuckDB, gratis, sin cuenta y reproducible con un
`git clone` (ADR 0001). En un equipo de datos real, los mismos modelos suelen ejecutarse en
un *lakehouse* en la nube, con gobierno de datos y cómputo gestionado. Se quería demostrar
eso sin perder la reproducibilidad local ni duplicar la lógica.

## Decisión

Databricks (Free Edition) es un **segundo destino del mismo proyecto dbt**, no un proyecto
aparte:

- **Unity Catalog:** catálogo `murcia_turismo` con los esquemas `raw` (volume `landing`),
  `bronze`, `silver`, `gold` y `ref`, los mismos nombres de capa que en DuckDB.
- **Bronze:** la interpretación de las fuentes sigue en un solo sitio (Python + DuckDB).
  Las tablas de bronze se exportan a Parquet, se suben al volume y se crean como tablas
  Delta con `read_files` (`murcia_data.databricks`).
- **dbt:** target `databricks` en `profiles.yml`. Las pocas funciones que se escriben
  distinto en cada motor están en macros con `adapter.dispatch`
  (`dbt/macros/portabilidad.sql`); ningún modelo tiene dos versiones.
- **Ejecución:** un Databricks Asset Bundle (`databricks.yml`) define un job que clona el
  repositorio y ejecuta `dbt build` en un SQL warehouse serverless. Lo lanza
  `publicar.yml` cada mes, después de cargar bronze.
- **Paridad:** tras cada ejecución se compara la «huella» de cada tabla de gold (filas y
  suma de cada columna numérica) entre DuckDB y Databricks. Si difieren, falla.
- **Credenciales:** ninguna en el repositorio. En local, OAuth con la CLI de Databricks;
  en GitHub Actions, un token en los secretos del repositorio.

## Alternativas descartadas

- **Databricks como único motor:** exige cuenta y conexión para cualquier cosa, incluida la
  CI de cada PR, y el repositorio dejaría de ser reproducible por cualquiera.
- **Parsear las fuentes en Databricks** (notebooks o PySpark): duplicaría la lógica de
  ingesta, que ya está probada en Python.
- **Mover la orquestación a Databricks Workflows:** Dagster sigue siendo el orquestador; el
  job de Databricks es una unidad de ejecución que se lanza desde la publicación mensual.

## Consecuencias

- Los mismos tests de dbt (de datos y unitarios) y los mismos contratos pasan en los dos motores, y gold es idéntico.
- Un modelo nuevo tiene que usar SQL común a los dos o una macro de portabilidad; la CI
  solo prueba DuckDB, así que la paridad se comprueba en la ejecución mensual.
- Free Edition tiene cuotas y no admite uso comercial: vale para este proyecto, y el resto
  de la publicación no depende de que Databricks esté disponible.
