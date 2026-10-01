# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido
- La caché de murciaturistica no volvía a pedir nunca un mes ya descargado (aunque la fuente lo
  revisara), y los meses sin publicar se borraban y se volvían a pedir en cada ejecución: con la
  fuente parada desde 2024, eran más de veinte peticiones inútiles por ejecución, y cada mes una
  más. Ahora se guardan todos y se revisan solo los seis últimos. La escritura en la caché es
  atómica, como la del INE.
- `release.py` borraba todo lo que hubiera en la carpeta de salida y sumaba cualquier fichero que
  encontrara en ella: ahora solo toca y suma los que genera.
- El informe y el test de dbt contaban de forma distinta los meses en los que cuadran las dos
  fuentes: ahora usan la misma tolerancia (10 unidades o el 0,05 %).
- `fct_precios_mensual.tipo_alojamiento_id` no tenía test de relación con su dimensión.
- `databricks-sdk` se usaba sin estar declarado (llegaba con `dbt-databricks`).
- La documentación decía 82 comprobaciones; son 100 (98 tests de dbt y 2 de Dagster).

## [2.1.0] - 2026-09-29

### Añadido
- Databricks como segundo destino del mismo proyecto dbt (ADR 0005): catálogo
  `murcia_turismo` en Unity Catalog, bronze subido a un volume y creado como tablas Delta,
  target `databricks` en dbt, macros de portabilidad, job definido en un Databricks Asset
  Bundle (`databricks.yml`) y test de paridad de gold entre DuckDB y Databricks. Se ejecuta
  en la publicación mensual si el repositorio tiene los secretos de Databricks.

## [2.0.0] - 2026-09-29

Plataforma de datos: dos fuentes, arquitectura por capas, dbt, Dagster y publicación
automática.

### Cambiado
- El informe web lee de la capa gold y amplía su alcance: hoteles, campings, apartamentos y
  turismo rural hasta el último mes publicado por el INE, empleo, precios hoteleros y el
  resultado de la validación cruzada entre fuentes. Todas las cifras siguen saliendo de los
  datos.
- El código pasa a ser el paquete `murcia_data` y las dependencias se gestionan con uv
  (`pyproject.toml` y `uv.lock`).
- La CI comprueba lint y formato con ruff antes de los tests.

### Eliminado
- El pipeline de pandas de la v1 (`pipeline.py`, `transform/`, `quality/`) y su salida en
  Parquet: su lógica está en dbt y reproduce las mismas cifras sin ninguna diferencia.

### Añadido
- Publicación en dos workflows: `ci.yml` (calidad en cada cambio, sin red) y
  `publicar.yml` (pipeline completo con Dagster, web, documentación de dbt con el grafo
  de linaje en `/docs/` y release mensual de datos).
- Release de datos `datos-AAAA-MM` (`murcia_data.release`): gold en Parquet y DuckDB, con
  `contrato.json` versionado y `SHA256SUMS`.
- Control de privacidad en pre-commit y en la CI: falla si algún fichero contiene rutas de
  un equipo personal o correos personales.
- Orquestación con Dagster (`murcia_data.definitions`): ingesta, bronze y modelos de dbt
  en un único grafo de *assets* con linaje de punta a punta; los tests de dbt se
  registran como comprobaciones, más dos propias sobre bronze (catálogo completo,
  bloqueante, y datos recientes del INE, de aviso). Trabajo `pipeline_mensual`
  programado el día 3 de cada mes a las 07:00 (hora de Madrid).
- Cliente de la API del INE con reintentos y espera exponencial; ingesta de las series a
  la capa raw (`data/raw/ine/<fecha>/<serie>.json`) con escritura atómica.
- Catálogo de 121 series del INE (`dbt/seeds/series_ine.csv`): demanda y oferta de
  hoteles, apartamentos, campings y turismo rural en la Región, la Costa Cálida,
  Cartagena y Murcia, y el índice de precios hoteleros de la Región y de España. Se
  genera a partir de los metadatos estructurados del INE con
  `scripts/generar_catalogo_ine.py`.
- Capa bronze en DuckDB (`data/warehouse.duckdb`): `bronze.ine_series` y
  `bronze.murciaturistica_destinos`, tipadas, con el secreto estadístico y las notas
  del INE, columnas de auditoría (`_fichero_origen`, `_ingestado_en`) y registro de
  cada carga en `bronze._cargas`.
- Proyecto dbt (`dbt/`) con la capa silver: staging 1:1 con bronze e intermedios con
  las reglas de negocio de la v1 en SQL (meses sin publicar, destino «no desglosado»
  por zona). Reproduce la tabla de hechos de la v1 sin ninguna diferencia (1.310 filas).
  Tests genéricos propios, tests singulares de negocio y tests unitarios de dbt.
- Capa gold en dbt con contratos: `dim_fecha`, `dim_territorio` (jerarquía de las dos
  fuentes), `dim_tipo_alojamiento`, `dim_residencia` y los hechos
  `fct_demanda_mensual`, `fct_oferta_mensual` y `fct_precios_mensual`. Hoteles,
  apartamentos, campings y turismo rural hasta agosto de 2026.
- Validación cruzada entre el INE y murciaturistica, con excepciones documentadas
  (ADR 0004).
- sqlfluff para el estilo del SQL y `dbt build` en la CI sobre un warehouse de prueba
  construido con los fixtures.
- pre-commit con ruff y comprobaciones básicas de ficheros.
- Dependabot para dependencias y GitHub Actions.
- ADR 0001-0003: DuckDB, Dagster y arquitectura por capas.

## [1.0.0] - 2026-09-29

### Añadido
- Ingesta de la serie mensual de viajeros y pernoctaciones por destino de
  murciaturistica.es (2015-2024), con caché local.
- Modelo en estrella (`fact_ocupacion`, `dim_destino`, `dim_fecha`) en Parquet.
- Corrección del secreto estadístico con un destino «no desglosado» por zona, validada
  contra los totales publicados.
- Exclusión de los meses que la fuente no publica.
- Informe web con indicadores y gráficos, publicado en GitHub Pages.
- Ejecución mensual en GitHub Actions.

[Sin publicar]: https://github.com/marnau74/murcia-open-data/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/marnau74/murcia-open-data/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/marnau74/murcia-open-data/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/marnau74/murcia-open-data/releases/tag/v1.0.0
