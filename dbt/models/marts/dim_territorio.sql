-- Territorios de las dos fuentes en una jerarquía explícita (padre_id). Cada fuente usa
-- una geografía distinta: la zona «Costa Cálida» del INE no es la «costa» de
-- murciaturistica. Nunca se suman territorios de niveles distintos.

select
    territorio_id,
    nombre,
    nivel,
    padre_id,
    fuente,
    nivel <> 'destino_mt' or nombre not like '%(no desglosado)' as es_desglosado

from {{ ref('territorios') }}
