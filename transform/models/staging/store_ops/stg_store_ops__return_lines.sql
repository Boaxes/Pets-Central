select
    id as return_line_id,
    sale_return_id as return_id,
    sale_line_id,
    quantity,
    refund_amount,
    restocked
from {{ source('store_ops', 'return_lines') }}
qualify row_number() over (partition by id order by _loaded_at desc) = 1
