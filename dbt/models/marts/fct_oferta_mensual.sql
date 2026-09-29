-- Oferta de alojamiento por mes, territorio y tipo: establecimientos, plazas, empleo y
-- grados de ocupación (en %). Cada tipo publica sus propias medidas (habitaciones en
-- hoteles, parcelas en campings...); las que no aplican quedan en NULL.

{%- set recuentos = [
    'establecimientos', 'plazas', 'habitaciones', 'apartamentos',
    'parcelas', 'parcelas_ocupadas', 'personal_empleado'
] %}
{%- set porcentajes = [
    'ocupacion_plazas', 'ocupacion_plazas_fin_semana', 'ocupacion_habitaciones',
    'ocupacion_apartamentos', 'ocupacion_apartamentos_fin_semana',
    'ocupacion_parcelas', 'ocupacion_parcelas_fin_semana'
] %}

with

pivotada as (
    select
        fecha,
        territorio as territorio_id,
        tipo_alojamiento as tipo_alojamiento_id,
        {%- for medida in recuentos + porcentajes %}
            max(valor) filter (where medida = '{{ medida }}') as {{ medida }},
        {%- endfor %}
        count(valor) as medidas_publicadas,
        bool_or(es_provisional) as es_provisional,
        bool_or(es_secreto) as tiene_secreto
    from {{ ref('int_ine__observaciones') }}
    where hecho = 'oferta'
    group by fecha, territorio, tipo_alojamiento
)

select
    strftime(fecha, '%Y%m')::integer as fecha_id,
    territorio_id,
    tipo_alojamiento_id,
    {%- for medida in recuentos %}
        {{ medida }}::bigint as {{ medida }},
    {%- endfor %}
    {%- for medida in porcentajes %}
        {{ medida }}::double as {{ medida }},
    {%- endfor %}
    es_provisional,
    tiene_secreto,
    'INE' as fuente

from pivotada

where medidas_publicadas > 0
