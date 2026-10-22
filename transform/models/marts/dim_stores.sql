select
    stores.store_id,
    stores.store_code,
    stores.store_name,
    stores.city,
    stores.state,
    stores.postal_code,
    stores.time_zone,
    regions.region_code,
    regions.region_name,
    stores.store_format,
    stores.original_chain,
    stores.original_chain <> 'pets_central' as is_acquired,
    stores.opened_on,
    stores.acquired_on,
    stores.closed_on,
    stores.joined_chain_on,
    stores.closed_on is null as is_open
from {{ ref('stg_store_ops__stores') }} as stores
inner join {{ ref('stg_store_ops__regions') }} as regions on regions.region_id = stores.region_id
