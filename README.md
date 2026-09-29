# Estacionalidad turística en la Región de Murcia

Pipeline de datos abiertos que ingiere estadística pública, la transforma a un
modelo dimensional y publica un informe interactivo. Proyecto de portfolio.

## La pregunta

¿Cómo se comporta la demanda hostelera y turística en la Región de Murcia a lo
largo del año, y qué diferencia hay entre los municipios de costa y los de
interior? El sector es fuertemente estacional; este proyecto lo cuantifica con
datos oficiales.

## Fuentes de datos

- **murciaturistica.es** (Instituto de Turismo de la Región de Murcia) — serie
  mensual de viajeros y pernoctaciones por destino turístico, reprocesada por
  el CREM a partir de la Encuesta de Ocupación Hotelera del INE. Es la fuente
  real del pipeline: ver `src/ingest/murciaturistica_client.py` para el
  porqué y las particularidades del endpoint (no documentado como API
  pública, descubierto navegando la web).

Datos públicos y reutilizables. Se descartaron tras explorarlos: el INE en
bruto (solo distingue Cartagena / Murcia capital / Costa Cálida, sin el
desglose de 11 destinos que sí ofrece la fuente elegida) y los portales CKAN
regionales/municipales (uno solo tiene directorios de establecimientos, no
series de demanda; el del Ayuntamiento de Murcia es inalcanzable).

## Arquitectura

```
murciaturistica.es (destinos)
      │  src/ingest/         cliente de solo lectura, con caché local
      ▼
data/raw/                    HTML crudo por mes (no versionado)
      │  src/transform/      construcción del modelo estrella (pandas)
      ▼
data/processed/*.parquet     fact + dimensiones
      │  src/quality/        validaciones (nulos, duplicados, integridad, rangos)
      ▼
Power BI                     informe publicado en Power BI Service
```

Orquestación: GitHub Actions ejecuta tests + pipeline el día 1 de cada mes.

### Modelo estrella

- `fact_ocupacion` — viajeros y pernoctaciones (residentes/no residentes) por destino/mes
- `dim_destino` — nombre y zona (ciudad / costa / interior), clasificación oficial
  del Instituto de Turismo, no inventada para este proyecto
- `dim_fecha` — fecha, año, mes, trimestre

### Secreto estadístico

Cuando el grado de respuesta de las encuestas es bajo, la fuente publica 0 en
los destinos individuales pero mantiene el subtotal real de la zona. Sumar
solo los destinos perdía 962.641 pernoctaciones de costa en 45 meses (casi
todos de invierno), lo que exageraba su estacionalidad: ratio agosto/enero de
9,6 en vez del 7,0 real. Por eso `dim_destino` incluye un miembro
`(no desglosado)` por zona que recoge esa diferencia —un 3,5% del total— y
`src/quality/` valida en cada ejecución que sumar una zona reproduce
exactamente el total publicado. La columna `desglosado` permite excluir esos
miembros del análisis por destino sin falsear los agregados por zona.

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
pytest -q                 # tests de calidad de datos
python -m src.pipeline    # ingesta + transformación + validación
```

## Estado

Pipeline funcional de punta a punta contra la fuente real (ingesta,
transformación, validación y guardado en Parquet). Pendiente: informe de
Power BI y ampliar el rango histórico ingerido más allá de 2015–2024.

## Stack

Python · pandas · requests · pyarrow · pytest · GitHub Actions · Power BI
