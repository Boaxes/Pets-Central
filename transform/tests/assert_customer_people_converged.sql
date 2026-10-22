-- Fails if any shared email or phone still links records labeled as different people,
-- meaning int_customer_people needs more rounds of label propagation.
with keys as (
    select people.person_id, 'email:' || customers.email_normalized as match_key
    from {{ ref('stg_store_ops__customers') }} as customers
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = customers.customer_id
    where customers.email_normalized is not null
    union all
    select people.person_id, 'phone:' || customers.phone_normalized
    from {{ ref('stg_store_ops__customers') }} as customers
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = customers.customer_id
    where customers.phone_normalized is not null
)

select match_key, count(distinct person_id) as people
from keys
group by match_key
having count(distinct person_id) > 1
