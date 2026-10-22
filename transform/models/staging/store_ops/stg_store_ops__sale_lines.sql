select
    id as sale_line_id,
    sale_id,
    line_number,
    product_id,
    animal_id,
    quantity,
    unit_price,
    unit_cost,
    discount_amount,
    quantity * unit_price as gross_amount,
    quantity * unit_price - discount_amount as net_amount,
    quantity * unit_cost as cost_amount
from {{ source('store_ops', 'sale_lines') }}
qualify row_number() over (partition by id order by updated_at desc, _loaded_at desc) = 1
