# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Cambiado
- El código pasa a ser el paquete `murcia_data` y las dependencias se gestionan con uv
  (`pyproject.toml` y `uv.lock`).
- La CI comprueba lint y formato con ruff antes de los tests.

### Añadido
- Cliente de la API del INE con reintentos y espera exponencial; ingesta de las series a
  la capa raw (`data/raw/ine/<fecha>/<serie>.json`) con escritura atómica.
- Catálogo de 121 series del INE (`dbt/seeds/series_ine.csv`): demanda y oferta de
  hoteles, apartamentos, campings y turismo rural en la Región, la Costa Cálida,
  Cartagena y Murcia, y el índice de precios hoteleros de la Región y de España. Se
  genera a partir de los metadatos estructurados del INE con
  `scripts/generar_catalogo_ine.py`.
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

[Sin publicar]: https://github.com/marnau74/murcia-open-data/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/marnau74/murcia-open-data/releases/tag/v1.0.0
