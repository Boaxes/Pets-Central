{# Drops every schema starting with DBT_SCHEMA_PREFIX: CI's clean-up after building a pull request. #}
{% macro drop_prefixed_schemas() %}
    {% set prefix = env_var('DBT_SCHEMA_PREFIX', '') | upper %}
    {% if not prefix %}
        {{ exceptions.raise_compiler_error('DBT_SCHEMA_PREFIX is not set; refusing to drop schemas.') }}
    {% endif %}
    {% set schemas = run_query("select schema_name from " ~ target.database ~ ".information_schema.schemata "
                               ~ "where schema_name like '" ~ prefix ~ "%'") %}
    {% for schema in schemas.columns[0].values() %}
        {% do run_query('drop schema if exists ' ~ target.database ~ '.' ~ schema) %}
        {{ log('Dropped ' ~ target.database ~ '.' ~ schema, info=True) }}
    {% endfor %}
{% endmacro %}
