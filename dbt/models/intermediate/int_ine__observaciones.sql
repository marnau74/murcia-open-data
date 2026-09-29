-- Observaciones del INE con las dimensiones del catálogo (seed series_ine). Solo entran
-- las series del catálogo; una serie del catálogo sin datos hace fallar un test.

select
    obs.fecha,
    obs.anio,
    obs.mes,
    cat.hecho,
    cat.tipo_alojamiento,
    cat.territorio,
    cat.nivel_territorio,
    cat.medida,
    nullif(cat.residencia, '') as residencia,
    obs.valor,
    obs.es_secreto,
    obs.es_provisional,
    obs.notas,
    obs.codigo

from {{ ref('stg_ine__series') }} as obs
inner join {{ ref('series_ine') }} as cat
    on obs.codigo = cat.codigo
