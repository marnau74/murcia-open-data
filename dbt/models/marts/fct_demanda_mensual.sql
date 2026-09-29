-- Viajeros y pernoctaciones por mes, territorio, tipo de alojamiento y residencia.
--
-- Une las dos fuentes sin solaparlas: el INE aporta la región, la Costa Cálida y los
-- municipios (los cuatro tipos de alojamiento); murciaturistica, los destinos
-- turísticos (solo hoteles). Una medida bajo secreto estadístico queda en NULL; un mes
-- sin ninguna medida publicada no tiene fila.

with

ine as (
    select
        fecha,
        territorio as territorio_id,
        tipo_alojamiento as tipo_alojamiento_id,
        residencia as residencia_id,
        max(valor) filter (where medida = 'viajeros') as viajeros,
        max(valor) filter (where medida = 'pernoctaciones') as pernoctaciones,
        bool_or(es_provisional) as es_provisional,
        bool_or(es_secreto) as tiene_secreto,
        'INE' as fuente
    from {{ ref('int_ine__observaciones') }}
    where hecho = 'demanda'
    group by fecha, territorio, tipo_alojamiento, residencia
),

mt_destinos as (
    select
        ocupacion.*,
        territorio.territorio_id
    from {{ ref('int_mt__ocupacion_destino') }} as ocupacion
    inner join {{ ref('territorios') }} as territorio
        on
            territorio.fuente = 'murciaturistica'
            and ocupacion.destino = territorio.nombre_en_fuente
),

mt as (
    select
        fecha,
        territorio_id,
        'hotel' as tipo_alojamiento_id,
        'espana' as residencia_id,
        viajeros_residentes as viajeros,
        pernoctaciones_residentes as pernoctaciones,
        false as es_provisional,
        false as tiene_secreto,
        'murciaturistica' as fuente
    from mt_destinos
    union all
    select
        fecha,
        territorio_id,
        'hotel' as tipo_alojamiento_id,
        'extranjero' as residencia_id,
        viajeros_no_residentes as viajeros,
        pernoctaciones_no_residentes as pernoctaciones,
        false as es_provisional,
        false as tiene_secreto,
        'murciaturistica' as fuente
    from mt_destinos
),

unida as (
    select * from ine
    union all
    select * from mt
)

select
    (year(fecha) * 100 + month(fecha))::integer as fecha_id,
    territorio_id,
    tipo_alojamiento_id,
    residencia_id,
    viajeros::bigint as viajeros,
    pernoctaciones::bigint as pernoctaciones,
    es_provisional,
    tiene_secreto,
    fuente

from unida

where viajeros is not null or pernoctaciones is not null
