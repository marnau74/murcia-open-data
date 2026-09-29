{#
    Funciones que se escriben distinto en DuckDB (desarrollo y CI) y en Databricks
    (segundo destino). Los modelos las usan a través de estas macros y nunca repiten su
    SQL para cada motor.
#}

{# Verdadero si `columna` contiene el patrón (expresión regular sin barras invertidas). #}
{% macro coincide_regex(columna, patron) -%}
    {{ return(adapter.dispatch('coincide_regex')(columna, patron)) }}
{%- endmacro %}

{% macro default__coincide_regex(columna, patron) -%}
    regexp_matches({{ columna }}, '{{ patron }}')
{%- endmacro %}

{% macro databricks__coincide_regex(columna, patron) -%}
    {{ columna }} rlike '{{ patron }}'
{%- endmacro %}


{# Una fila por mes entre las columnas `desde` y `hasta` de `tabla` (fechas). #}
{% macro meses_entre(tabla, desde, hasta) -%}
    {{ return(adapter.dispatch('meses_entre')(tabla, desde, hasta)) }}
{%- endmacro %}

{% macro default__meses_entre(tabla, desde, hasta) -%}
    select unnest(generate_series({{ desde }}, {{ hasta }}, interval 1 month))::date as fecha
    from {{ tabla }}
{%- endmacro %}

{% macro databricks__meses_entre(tabla, desde, hasta) -%}
    select explode(sequence({{ desde }}, {{ hasta }}, interval 1 month)) as fecha
    from {{ tabla }}
{%- endmacro %}
