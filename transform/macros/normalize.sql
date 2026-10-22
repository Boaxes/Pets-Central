{# Shared cleaning rules, so every source normalizes the same way. #}

{% macro normalize_email(column) -%}
    {%- set cleaned = 'nullif(lower(trim(' ~ column ~ ')), \'\')' -%}
    {%- for typo, fix in var('email_domain_typos').items() -%}
        {%- set cleaned = 'replace(' ~ cleaned ~ ', \'' ~ typo ~ '\', \'' ~ fix ~ '\')' -%}
    {%- endfor -%}
    {{ cleaned }}
{%- endmacro %}

{# Ten digits, or null: drops punctuation and a leading US country code. #}
{% macro normalize_phone(column) -%}
    case
        when length(regexp_replace({{ column }}, '[^0-9]', '')) = 11
             and left(regexp_replace({{ column }}, '[^0-9]', ''), 1) = '1'
            then right(regexp_replace({{ column }}, '[^0-9]', ''), 10)
        when length(regexp_replace({{ column }}, '[^0-9]', '')) = 10
            then regexp_replace({{ column }}, '[^0-9]', '')
    end
{%- endmacro %}

{# Letters only, lowercase, for comparing names. #}
{% macro normalize_name(column) -%}
    nullif(regexp_replace(lower({{ column }}), '[^a-z]', ''), '')
{%- endmacro %}

{% macro to_utc(column) -%}
    convert_timezone('UTC', {{ column }})::timestamp_ntz
{%- endmacro %}

{# Coupon codes as campaigns define them: uppercase, no spaces. #}
{% macro normalize_coupon_code(column) -%}
    nullif(upper(replace({{ column }}, ' ', '')), '')
{%- endmacro %}

{# The loyalty platform's store codes to the store system's: PC0042 -> PC-0042, CC-WA-017 -> CC/WA/017. #}
{% macro store_code_from_loyalty(column) -%}
    case
        when {{ column }} like 'PC%' then 'PC-' || substr({{ column }}, 3)
        when {{ column }} like 'CC-%' then replace({{ column }}, '-', '/')
    end
{%- endmacro %}
