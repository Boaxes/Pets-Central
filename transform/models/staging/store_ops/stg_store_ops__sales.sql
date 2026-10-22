select
    id as sale_id,
    receipt_number,
    store_id,
    customer_id,
    employee_id,
    channel,
    status,
    status = 'cancelled' as is_cancelled,
    {{ to_utc('sold_at') }} as sold_at_utc,
    {{ to_utc('cancelled_at') }} as cancelled_at_utc,
    nullif(coupon_code, '') as coupon_code_as_typed,
    {{ normalize_coupon_code('coupon_code') }} as coupon_code
from {{ source('store_ops', 'sales') }}
qualify row_number() over (partition by id order by updated_at desc, _loaded_at desc) = 1
