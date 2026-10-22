-- One row per sale line, cancelled sales included (filter on is_cancelled). Amounts are in dollars.
-- sale_date is the store's local date, which is what "sales on Black Friday" means.
select
    lines.sale_line_id,
    lines.sale_id,
    lines.line_number,
    sales.receipt_number,
    sales.sold_at_utc,
    convert_timezone('UTC', stores.time_zone, sales.sold_at_utc) as sold_at_local,
    convert_timezone('UTC', stores.time_zone, sales.sold_at_utc)::date as sale_date,
    sales.store_id,
    lines.product_id,
    lines.animal_id,
    sales.customer_id,
    people.person_id,
    sales.customer_id is null as is_guest,
    person_members.member_id is not null as is_member,
    sales.employee_id,
    sales.channel,
    sales.is_cancelled,
    campaigns.campaign_id as coupon_campaign_id,
    lines.quantity,
    lines.unit_price,
    lines.unit_cost,
    lines.gross_amount,
    lines.discount_amount,
    lines.net_amount,
    lines.cost_amount,
    lines.net_amount - lines.cost_amount as gross_margin
from {{ ref('stg_store_ops__sale_lines') }} as lines
inner join {{ ref('stg_store_ops__sales') }} as sales on sales.sale_id = lines.sale_id
inner join {{ ref('stg_store_ops__stores') }} as stores on stores.store_id = sales.store_id
left join {{ ref('int_customer_people') }} as people on people.customer_id = sales.customer_id
left join {{ ref('int_person_members') }} as person_members on person_members.person_id = people.person_id
left join {{ ref('stg_loyalty__campaigns') }} as campaigns on campaigns.campaign_code = sales.coupon_code
