-- One row per sale (receipt).
select
    sale_id,
    receipt_number,
    sold_at_utc,
    sold_at_local,
    sale_date,
    store_id,
    customer_id,
    person_id,
    is_guest,
    is_member,
    employee_id,
    channel,
    is_cancelled,
    coupon_campaign_id,
    count(*) as line_count,
    sum(quantity) as item_count,
    sum(gross_amount) as gross_amount,
    sum(discount_amount) as discount_amount,
    sum(net_amount) as net_amount,
    sum(cost_amount) as cost_amount,
    sum(gross_margin) as gross_margin
from {{ ref('fct_sale_lines') }}
group by all
