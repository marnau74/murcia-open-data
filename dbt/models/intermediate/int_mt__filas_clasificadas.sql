-- Cada fila publicada con su zona y su tipo (destino, subtotal, total de zona o total
-- regional), solo en los meses publicados.

select
    stg.fecha,
    stg.destino,
    dest.zona,
    dest.tipo_fila,
    stg.tiene_llamada,
    stg.viajeros_residentes,
    stg.viajeros_no_residentes,
    stg.pernoctaciones_residentes,
    stg.pernoctaciones_no_residentes

from {{ ref('stg_mt__destinos') }} as stg
inner join {{ ref('int_mt__meses_publicados') }} as pub
    on stg.fecha = pub.fecha
inner join {{ ref('destinos_murciaturistica') }} as dest
    on stg.destino = dest.destino
