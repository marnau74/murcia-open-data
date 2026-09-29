-- Observaciones mensuales del INE, con nombres y tipos del proyecto.
-- Un valor bajo secreto estadístico pasa a NULL: el INE no lo publica, y un 0 sería falso.

select
    codigo,
    make_date(anio, periodo, 1) as fecha,
    anio,
    periodo as mes,
    case when secreto then null else valor end as valor,
    secreto as es_secreto,
    fk_tipo_dato = 2 as es_provisional,
    notas,
    _ingestado_en

from {{ source('bronze', 'ine_series') }}
