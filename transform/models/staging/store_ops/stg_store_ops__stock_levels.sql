-- A snapshot: the loader replaces this table on every run, so its load time is the snapshot time.
select
    id as stock_level_id,
    store_id,
    product_id,
    quantity_on_hand,
    reorder_point,
    {{ to_utc('_loaded_at') }} as snapshot_at_utc
from {{ source('store_ops', 'stock_levels') }}
