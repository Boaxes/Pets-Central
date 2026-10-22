{# Models go in the schema they name (STAGING, MARTS...), not ANALYTICS_STAGING. CI sets DBT_SCHEMA_PREFIX (PR_12_)
   so each pull request builds into its own schemas, dropped afterwards by drop_prefixed_schemas. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (env_var('DBT_SCHEMA_PREFIX', '') ~ (custom_schema_name or target.schema)) | trim | upper }}
{%- endmacro %}
