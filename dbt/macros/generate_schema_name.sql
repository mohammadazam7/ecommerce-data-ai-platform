{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Use `staging` and `marts` as written instead of dbt's default `main_marts`. -#}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
