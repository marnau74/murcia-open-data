-- Sumar los destinos de una zona (incluido el «no desglosado») debe reproducir el total
-- que publica la fuente para esa zona y mes. Devuelve las celdas que no cuadran.

with

sumado as (
    select
        fecha,
        zona,
        sum(viajeros_residentes) as viajeros_residentes,
        sum(viajeros_no_residentes) as viajeros_no_residentes,
        sum(pernoctaciones_residentes) as pernoctaciones_residentes,
        sum(pernoctaciones_no_residentes) as pernoctaciones_no_residentes
    from {{ ref('int_mt__ocupacion_destino') }}
    group by fecha, zona
),

publicado as (
    select * from {{ ref('int_mt__filas_clasificadas') }}
    where tipo_fila = 'total_zona'
)

select
    publicado.fecha,
    publicado.zona

from publicado
left join sumado
    on publicado.fecha = sumado.fecha and publicado.zona = sumado.zona

where
    abs(coalesce(sumado.viajeros_residentes, 0) - publicado.viajeros_residentes) > 0.5
    or abs(coalesce(sumado.viajeros_no_residentes, 0) - publicado.viajeros_no_residentes) > 0.5
    or abs(coalesce(sumado.pernoctaciones_residentes, 0) - publicado.pernoctaciones_residentes) > 0.5
    or abs(coalesce(sumado.pernoctaciones_no_residentes, 0) - publicado.pernoctaciones_no_residentes) > 0.5
