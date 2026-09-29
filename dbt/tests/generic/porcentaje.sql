{#- Un grado de ocupación es un porcentaje entre 0 y 100. -#}
{% test porcentaje(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0 or {{ column_name }} > 100

{% endtest %}
