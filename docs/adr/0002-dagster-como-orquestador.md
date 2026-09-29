# 0002 · Dagster como orquestador

- **Estado:** aceptada
- **Fecha:** 2026-09-29

## Contexto

El pipeline pasa de un script secuencial a varios pasos con dependencias: ingesta de
cada fuente, carga en bronze, modelos de dbt y comprobaciones de calidad. Hace falta
ejecutar solo lo necesario, ver el linaje de punta a punta y programar una ejecución
mensual, tanto en local como en GitHub Actions.

## Decisión

Usar **Dagster** con *software-defined assets*. Cada tabla o fichero es un *asset*, los
modelos de dbt se cargan como *assets* con `dagster-dbt` y las validaciones son *asset
checks*.

## Alternativas descartadas

- **Airflow:** está orientado a tareas, no a datos, y necesita *scheduler* y base de datos
  siempre encendidos. Para una ejecución al mes es desproporcionado.
- **Prefect:** también es válido, pero su modelo gira en torno a tareas y flujos. El de
  Dagster, centrado en los datos (*assets*), encaja mejor con dbt, donde cada modelo ya
  es una tabla.
- **Seguir con un script y cron:** sin linaje, sin reintentos por paso y sin forma de
  materializar solo una parte.

## Consecuencias

- El grafo de Dagster muestra el recorrido completo, de la API del INE al mart final.
- En la CI se ejecuta con `dagster asset materialize`, sin servidor.
- `dagster-dbt` todavía no admite Python 3.14: el proyecto fija `>=3.12,<3.14`.
