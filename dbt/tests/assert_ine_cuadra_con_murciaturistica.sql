-- Validación cruzada entre fuentes. murciaturistica y el INE salen de la misma encuesta
-- (la EOH): la suma de los destinos turísticos debe coincidir con el total hotelero
-- regional del INE en cada mes que publican las dos.
--
-- Tolerancia: murciaturistica suma destinos ya redondeados, así que se admiten
-- diferencias de redondeo (máximo observado: 5 pernoctaciones en un mes de ~300.000).
-- Se marca como error una diferencia de más de 10 unidades y del 0,05 % (el informe usa la
-- misma tolerancia: murcia_data.report.indicadores.TOLERANCIA_CUADRE).
--
-- Las diferencias ya estudiadas y documentadas están en el seed `excepciones_cuadre`
-- (con su motivo): se excluyen solo para esa medida y ese mes.

with

ine as (
    select
        demanda.fecha_id,
        sum(demanda.viajeros) as viajeros,
        sum(demanda.pernoctaciones) as pernoctaciones
    from {{ ref('fct_demanda_mensual') }} as demanda
    where
        demanda.fuente = 'INE'
        and demanda.territorio_id = 'region-murcia'
        and demanda.tipo_alojamiento_id = 'hotel'
    group by demanda.fecha_id
),

destinos as (
    select
        demanda.fecha_id,
        sum(demanda.viajeros) as viajeros,
        sum(demanda.pernoctaciones) as pernoctaciones
    from {{ ref('fct_demanda_mensual') }} as demanda
    where demanda.fuente = 'murciaturistica'
    group by demanda.fecha_id
)

select
    ine.fecha_id,
    ine.pernoctaciones as pernoctaciones_ine,
    destinos.pernoctaciones as pernoctaciones_destinos,
    ine.viajeros as viajeros_ine,
    destinos.viajeros as viajeros_destinos

from ine
inner join destinos
    on ine.fecha_id = destinos.fecha_id

where
    (
        abs(ine.pernoctaciones - destinos.pernoctaciones) > 10
        and abs(ine.pernoctaciones - destinos.pernoctaciones) > 0.0005 * ine.pernoctaciones
        and ine.fecha_id not in (
            select excepcion.fecha_id from {{ ref('excepciones_cuadre') }} as excepcion
            where excepcion.medida = 'pernoctaciones'
        )
    )
    or (
        abs(ine.viajeros - destinos.viajeros) > 10
        and abs(ine.viajeros - destinos.viajeros) > 0.0005 * ine.viajeros
        and ine.fecha_id not in (
            select excepcion.fecha_id from {{ ref('excepciones_cuadre') }} as excepcion
            where excepcion.medida = 'viajeros'
        )
    )
