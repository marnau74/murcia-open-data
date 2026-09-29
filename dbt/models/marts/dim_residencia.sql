select
    residencia_id,
    nombre

from {{ ref('residencias') }}
