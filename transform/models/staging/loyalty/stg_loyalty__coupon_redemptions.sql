select
    record:redemption_id::varchar as redemption_id,
    record:campaign_id::int as campaign_id,
    {{ normalize_coupon_code('record:coupon_code::varchar') }} as coupon_code,
    record:member_id::varchar as member_id,
    record:store_code::varchar as store_code_loyalty,
    {{ store_code_from_loyalty('record:store_code::varchar') }} as store_code,
    {{ to_utc('record:redeemed_at::timestamp_tz') }} as redeemed_at_utc,
    record:order_total::number(12, 2) as order_total,
    record:discount_amount::number(12, 2) as discount_amount,
    record:status::varchar as status,
    {{ to_utc('record:voided_at::timestamp_tz') }} as voided_at_utc,
    {{ to_utc('changed_at') }} as recorded_at_utc
from {{ source('loyalty', 'coupon_redemptions') }}
qualify row_number() over (partition by record_id order by changed_at desc, _loaded_at desc) = 1
