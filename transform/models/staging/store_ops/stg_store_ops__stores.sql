select
    id as store_id,
    store_code,
    name as store_name,
    region_id,
    original_chain,
    store_format,
    address_line,
    city,
    state,
    postal_code,
    time_zone,
    opened_on,
    acquired_on,
    closed_on,
    -- The first day this store's sales are in the system: acquired stores join on their acquisition date.
    coalesce(acquired_on, opened_on) as joined_chain_on
from {{ source('store_ops', 'stores') }}
