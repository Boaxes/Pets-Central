-- The two systems must agree on coupon use: for each campaign, the loyalty platform's redemptions (voided ones
-- included) match the store's sales with that coupon code, in count and in money.
with platform as (
    select campaign_id, count(*) as redemptions, sum(order_total) as order_total
    from {{ ref('fct_coupon_redemptions') }}
    group by campaign_id
),

store as (
    select coupon_campaign_id as campaign_id, count(*) as sales, sum(net_amount) as net_amount
    from {{ ref('fct_sales') }}
    where coupon_campaign_id is not null
    group by coupon_campaign_id
)

select coalesce(platform.campaign_id, store.campaign_id) as campaign_id, platform.redemptions, store.sales,
       platform.order_total, store.net_amount
from platform
full outer join store on store.campaign_id = platform.campaign_id
where coalesce(platform.redemptions, 0) <> coalesce(store.sales, 0)
   or abs(coalesce(platform.order_total, 0) - coalesce(store.net_amount, 0)) > 0.01
