-- Lo que la fuente publica en el total de una zona pero no desglosa por destino.
--
-- Cuando pocos establecimientos responden a la encuesta, murciaturistica pone 0 en los
-- destinos (secreto estadístico) pero mantiene el total real de la zona. Sin este
-- residual la costa pierde casi un millón de pernoctaciones, sobre todo de invierno, y
-- su estacionalidad sale exagerada. Solo genera fila si hay algo que recuperar; nunca
-- negativa (una suma de destinos mayor que el total sería un error de la fuente).

with

totales as (
    select * from {{ ref('int_mt__filas_clasificadas') }}
    where tipo_fila = 'total_zona'
),

destinos as (
    select
        fecha,
        zona,
        sum(viajeros_residentes) as viajeros_residentes,
        sum(viajeros_no_residentes) as viajeros_no_residentes,
        sum(pernoctaciones_residentes) as pernoctaciones_residentes,
        sum(pernoctaciones_no_residentes) as pernoctaciones_no_residentes
    from {{ ref('int_mt__filas_clasificadas') }}
    where tipo_fila = 'destino'
    group by fecha, zona
),

residual as (
    select
        totales.fecha,
        totales.zona,
        greatest(totales.viajeros_residentes - coalesce(destinos.viajeros_residentes, 0), 0)
            as viajeros_residentes,
        greatest(totales.viajeros_no_residentes - coalesce(destinos.viajeros_no_residentes, 0), 0)
            as viajeros_no_residentes,
        greatest(totales.pernoctaciones_residentes - coalesce(destinos.pernoctaciones_residentes, 0), 0)
            as pernoctaciones_residentes,
        greatest(totales.pernoctaciones_no_residentes - coalesce(destinos.pernoctaciones_no_residentes, 0), 0)
            as pernoctaciones_no_residentes
    from totales
    left join destinos
        on totales.fecha = destinos.fecha and totales.zona = destinos.zona
)

select *

from residual

where
    viajeros_residentes + viajeros_no_residentes
    + pernoctaciones_residentes + pernoctaciones_no_residentes > 0
