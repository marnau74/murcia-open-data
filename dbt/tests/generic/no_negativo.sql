{#- Viajeros, pernoctaciones, plazas o personal nunca pueden ser negativos. -#}
{% test no_negativo(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0

{% endtest %}
