-- Todo destino de murciaturistica debe tener su territorio en el seed `territorios`: la
-- tabla de hechos los une con un inner join y, sin este test, un destino nuevo o
-- renombrado desaparecería en silencio.

select distinct ocupacion.destino

from {{ ref('int_mt__ocupacion_destino') }} as ocupacion
left join {{ ref('territorios') }} as territorio
    on
        territorio.fuente = 'murciaturistica'
        and ocupacion.destino = territorio.nombre_en_fuente

where territorio.territorio_id is null
