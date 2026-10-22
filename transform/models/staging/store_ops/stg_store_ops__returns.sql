select
    id as return_id,
    return_number,
    sale_id,
    store_id,
    employee_id,
    reason,
    {{ to_utc('returned_at') }} as returned_at_utc
from {{ source('store_ops', 'returns') }}
-- Returns never change, but a re-run could load one twice.
qualify row_number() over (partition by id order by _loaded_at desc) = 1
