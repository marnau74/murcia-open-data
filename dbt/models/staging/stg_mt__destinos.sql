-- Filas publicadas por murciaturistica.es. Los subtotales llevan una llamada (* o #)
-- en los meses en que la fuente oculta los destinos por secreto estadístico: se quita
-- de la etiqueta y se conserva como marca.

select
    make_date(anio, mes, 1) as fecha,
    anio,
    mes,
    trim(regexp_replace(destino, '\s*[*#]+$', '')) as destino,
    regexp_matches(destino, '[*#]\s*$') as tiene_llamada,
    viajeros_residentes,
    viajeros_no_residentes,
    pernoctaciones_residentes,
    pernoctaciones_no_residentes,
    _ingestado_en

from {{ source('bronze', 'murciaturistica_destinos') }}
