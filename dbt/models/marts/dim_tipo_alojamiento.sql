select
    tipo_alojamiento_id,
    nombre,
    encuesta_ine

from {{ ref('tipos_alojamiento') }}
