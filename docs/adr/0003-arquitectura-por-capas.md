# 0003 · Arquitectura por capas (raw, bronze, silver, gold)

- **Estado:** aceptada
- **Fecha:** 2026-09-29

## Contexto

En la v1, ingesta, limpieza y modelo estaban en el mismo flujo de pandas. Al añadir
fuentes con formatos y geografías distintas hace falta separar responsabilidades: poder
reprocesar sin volver a descargar, saber de dónde sale cada dato y tener un único punto
de consumo estable.

## Decisión

Organizar los datos en cuatro capas:

| Capa | Dónde | Contenido | Regla |
|---|---|---|---|
| raw | `data/raw/<fuente>/` | Respuestas originales (JSON, HTML) | Inmutable; solo se añade |
| bronze | DuckDB, esquema `bronze` | Una tabla por fuente, tipada y con columnas de auditoría | Sin lógica de negocio |
| silver | dbt `staging` e `intermediate` | Datos limpios, normalizados y con las reglas de negocio | Una vista por concepto |
| gold | dbt `marts` | Modelo en estrella con contratos | Lo único que se consume |

## Alternativas descartadas

- **Transformar directamente desde la respuesta de la fuente:** obliga a volver a
  descargar para cualquier cambio y pierde la trazabilidad.
- **Solo dos capas (crudo y final):** mezcla limpieza y modelado y hace difícil probarlos
  por separado.

## Consecuencias

- La web, las *releases* de datos y la API solo leen gold: se puede refactorizar silver
  sin romper a nadie mientras se respeten los contratos.
- Los nombres de capa son los mismos en DuckDB y en Databricks (fase 8).
- Más modelos que mantener; se compensa con convenciones de nombres y tests en cada
  capa.
