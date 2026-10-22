-- One row per person: duplicate customer records merged (int_customer_people), with their loyalty membership
-- (int_person_members) and what they have bought. Names and home store come from their first record.
with records as (
    select customers.*, people.person_id, people.records_for_person
    from {{ ref('stg_store_ops__customers') }} as customers
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = customers.customer_id
),

first_records as (
    select * from records
    qualify row_number() over (partition by person_id order by created_at_utc, customer_id) = 1
),

purchases as (
    select
        person_id,
        min(sold_at_utc) as first_purchase_at_utc,
        max(sold_at_utc) as last_purchase_at_utc,
        count(*) as purchases,
        sum(net_amount) as lifetime_net_amount,
        sum(gross_margin) as lifetime_gross_margin
    from {{ ref('fct_sales') }}
    where not is_cancelled and person_id is not null
    group by person_id
),

contact as (
    select person_id, boolor_agg(marketing_opt_in) as marketing_opt_in, min(created_at_utc) as first_seen_at_utc
    from records
    group by person_id
)

select
    first_records.person_id,
    first_records.first_name,
    first_records.last_name,
    first_records.home_store_id,
    first_records.postal_code,
    first_records.records_for_person as customer_records,
    contact.first_seen_at_utc,
    contact.marketing_opt_in,
    members.member_id is not null as is_loyalty_member,
    members.member_id,
    members.tier as loyalty_tier,
    members.status as loyalty_status,
    members.email_opt_in as loyalty_email_opt_in,
    members.pet_types,
    members.enrolled_at_utc as loyalty_enrolled_at_utc,
    members.points_balance,
    members.match_method as loyalty_match_method,
    purchases.first_purchase_at_utc,
    purchases.last_purchase_at_utc,
    coalesce(purchases.purchases, 0) as purchases,
    coalesce(purchases.lifetime_net_amount, 0) as lifetime_net_amount,
    coalesce(purchases.lifetime_gross_margin, 0) as lifetime_gross_margin,
    case
        when purchases.purchases is null then 'never purchased'
        when purchases.purchases = 1 then 'one-time'
        else 'repeat'
    end as customer_type
from first_records
inner join contact on contact.person_id = first_records.person_id
left join {{ ref('int_person_members') }} as members on members.person_id = first_records.person_id
left join purchases on purchases.person_id = first_records.person_id
