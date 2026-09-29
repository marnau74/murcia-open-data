-- Calendario mensual que cubre todas las fuentes, sin huecos (un mes sin datos existe en
-- el calendario aunque no tenga hechos).

with

fechas as (
    select fecha from {{ ref('int_ine__observaciones') }}
    union all
    select fecha from {{ ref('int_mt__ocupacion_destino') }}
),

meses as (
    select unnest(generate_series(min(fecha), max(fecha), interval 1 month))::date as fecha
    from fechas
)

select
    strftime(fecha, '%Y%m')::integer as fecha_id,
    fecha,
    year(fecha)::smallint as anio,
    month(fecha)::smallint as mes,
    quarter(fecha)::smallint as trimestre,
    [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ][month(fecha)] as nombre_mes

from meses
