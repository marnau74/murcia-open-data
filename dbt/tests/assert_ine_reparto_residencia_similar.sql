-- Aviso (no error): el reparto entre residentes en España y en el extranjero no coincide
-- exactamente entre murciaturistica y el INE, aunque el total sí. Las diferencias se
-- compensan entre sí (lo que sobra en un grupo falta en el otro) y en el año suponen como
-- mucho 0,11 puntos de peso del turismo extranjero. Se avisa si un mes se desvía más de
-- un 5 % en alguno de los dos grupos, para detectar un cambio de criterio en la fuente.
{{ config(severity='warn') }}

with

ine as (
    select
        fecha_id,
        residencia_id,
        sum(pernoctaciones) as pernoctaciones
    from {{ ref('fct_demanda_mensual') }}
    where
        fuente = 'INE'
        and territorio_id = 'region-murcia'
        and tipo_alojamiento_id = 'hotel'
    group by fecha_id, residencia_id
),

destinos as (
    select
        fecha_id,
        residencia_id,
        sum(pernoctaciones) as pernoctaciones
    from {{ ref('fct_demanda_mensual') }}
    where fuente = 'murciaturistica'
    group by fecha_id, residencia_id
)

select
    ine.fecha_id,
    ine.residencia_id,
    ine.pernoctaciones as pernoctaciones_ine,
    destinos.pernoctaciones as pernoctaciones_destinos

from ine
inner join destinos
    on ine.fecha_id = destinos.fecha_id and ine.residencia_id = destinos.residencia_id

where abs(ine.pernoctaciones - destinos.pernoctaciones) > 0.05 * ine.pernoctaciones
