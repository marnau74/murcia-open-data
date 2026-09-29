-- Calendario mensual que cubre todas las fuentes, sin huecos (un mes sin datos existe en
-- el calendario aunque no tenga hechos).

with

fechas as (
    select fecha from {{ ref('int_ine__observaciones') }}
    union all
    select fecha from {{ ref('int_mt__ocupacion_destino') }}
),

limites as (
    select
        min(fecha) as desde,
        max(fecha) as hasta
    from fechas
),

meses as (
    {{ meses_entre('limites', 'desde', 'hasta') }}
)

{%- set nombres_mes = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
] %}

select
    (year(fecha) * 100 + month(fecha))::integer as fecha_id,
    fecha,
    year(fecha)::smallint as anio,
    month(fecha)::smallint as mes,
    quarter(fecha)::smallint as trimestre,
    case month(fecha)
        {%- for nombre in nombres_mes %}
            when {{ loop.index }} then '{{ nombre }}'
        {%- endfor %}
    end as nombre_mes

from meses
