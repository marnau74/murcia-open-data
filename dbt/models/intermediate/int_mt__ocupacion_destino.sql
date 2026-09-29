-- Ocupación hotelera por destino y mes: los 11 destinos oficiales más un destino
-- «(no desglosado)» por zona con el residual. Sumar una zona reproduce siempre el total
-- publicado (lo comprueba tests/assert_mt_zonas_cuadran_con_totales.sql).

select
    fecha,
    destino,
    zona,
    true as desglosado,
    viajeros_residentes,
    viajeros_no_residentes,
    pernoctaciones_residentes,
    pernoctaciones_no_residentes

from {{ ref('int_mt__filas_clasificadas') }}

where tipo_fila = 'destino'

union all

select
    fecha,
    upper(zona[1]) || zona[2:] || ' (no desglosado)' as destino,
    zona,
    false as desglosado,
    viajeros_residentes,
    viajeros_no_residentes,
    pernoctaciones_residentes,
    pernoctaciones_no_residentes

from {{ ref('int_mt__residual_por_zona') }}
