-- What each store has on the shelf as of the last load, valued at current prices.
select
    stock.stock_level_id,
    stock.store_id,
    stock.product_id,
    stock.snapshot_at_utc,
    stock.quantity_on_hand,
    stock.reorder_point,
    stock.quantity_on_hand <= stock.reorder_point as needs_reorder,
    stock.quantity_on_hand = 0 as is_out_of_stock,
    stock.quantity_on_hand * products.current_list_price as retail_value,
    stock.quantity_on_hand * products.current_unit_cost as cost_value
from {{ ref('stg_store_ops__stock_levels') }} as stock
inner join {{ ref('dim_products') }} as products on products.product_id = stock.product_id
