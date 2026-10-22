select
    id as product_price_id,
    product_id,
    list_price,
    unit_cost,
    {{ to_utc('valid_from') }} as valid_from_utc,
    {{ to_utc('valid_to') }} as valid_to_utc,
    valid_to is null as is_current
from {{ source('store_ops', 'product_prices') }}
-- RAW keeps every version of a row; use the latest.
qualify row_number() over (partition by id order by updated_at desc, _loaded_at desc) = 1
