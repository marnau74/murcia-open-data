-- Necesita la ingesta completa: en la CI (con fixtures) se excluye por la etiqueta.
{{ config(tags=['datos_completos']) }}

-- Toda serie del catálogo debe tener datos en la última ingesta. Si el INE deja de
-- publicar una serie o cambia su código, este test lo detecta.

select cat.codigo

from {{ ref('series_ine') }} as cat
left join {{ ref('stg_ine__series') }} as obs
    on cat.codigo = obs.codigo

where obs.codigo is null
