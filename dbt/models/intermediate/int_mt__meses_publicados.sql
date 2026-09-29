-- Meses que murciaturistica ha publicado de verdad. Para los que no (marzo-junio y
-- diciembre de 2020, y todo lo posterior a diciembre de 2024) la fuente devuelve la
-- tabla entera a 0: no son meses sin turistas, son datos ausentes.

select fecha

from {{ ref('stg_mt__destinos') }}

group by fecha

having
    sum(
        coalesce(viajeros_residentes, 0)
        + coalesce(viajeros_no_residentes, 0)
        + coalesce(pernoctaciones_residentes, 0)
        + coalesce(pernoctaciones_no_residentes, 0)
    ) > 0
