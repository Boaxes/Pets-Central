-- One row per coupon code used at the register, as the loyalty platform recorded it.
select
    redemptions.redemption_id,
    redemptions.campaign_id,
    redemptions.coupon_code,
    redemptions.member_id,
    matches.person_id,
    redemptions.member_id is not null as by_member,
    stores.store_id,
    redemptions.redeemed_at_utc,
    convert_timezone('UTC', stores.time_zone, redemptions.redeemed_at_utc)::date as redeemed_date,
    redemptions.order_total,
    redemptions.discount_amount,
    redemptions.status,
    redemptions.status = 'voided' as is_voided,
    redemptions.voided_at_utc
from {{ ref('stg_loyalty__coupon_redemptions') }} as redemptions
left join {{ ref('int_member_matches') }} as matches on matches.member_id = redemptions.member_id
left join {{ ref('stg_store_ops__stores') }} as stores on stores.store_code = redemptions.store_code
