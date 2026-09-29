-- Índice de precios hoteleros (base 2008) y su variación interanual (%), de la Región de
-- Murcia y del total de España para poder compararlos.

with

pivotada as (
    select
        fecha,
        territorio as territorio_id,
        tipo_alojamiento as tipo_alojamiento_id,
        max(valor) filter (where medida = 'indice_precios') as indice_precios,
        max(valor) filter (where medida = 'variacion_interanual_precios') as variacion_interanual,
        bool_or(es_provisional) as es_provisional
    from {{ ref('int_ine__observaciones') }}
    where hecho = 'precios'
    group by fecha, territorio, tipo_alojamiento
)

select
    strftime(fecha, '%Y%m')::integer as fecha_id,
    territorio_id,
    tipo_alojamiento_id,
    indice_precios::double as indice_precios,
    variacion_interanual::double as variacion_interanual,
    es_provisional,
    'INE' as fuente

from pivotada

where indice_precios is not null or variacion_interanual is not null
