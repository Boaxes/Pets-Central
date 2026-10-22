-- Which person each loyalty member is. Members share no ID with store customers, so they are matched on contact
-- details normalized the same way on both sides:
--
-- 1. Email: the member's email belongs to exactly one person. The strongest evidence.
-- 2. Phone and last name: used only when the email finds no one. A phone alone is weaker (numbers get reassigned,
--    households share them), so the last name must agree too.
-- 3. Full name and postal code: the weakest, used only when neither email nor phone finds anyone, and only when
--    exactly one person in that postal code has that name.
--
-- When the evidence points at more than one person, the member is left unmatched rather than guessed at.
-- has_conflict marks members whose email and phone point at different people; email wins.

with members as (
    select member_id, email_normalized, phone_normalized, first_name_normalized, last_name_normalized, postal_code
    from {{ ref('stg_loyalty__members') }}
),

customers as (
    select
        customers.email_normalized,
        customers.phone_normalized,
        customers.first_name_normalized,
        customers.last_name_normalized,
        customers.postal_code,
        people.person_id
    from {{ ref('stg_store_ops__customers') }} as customers
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = customers.customer_id
),

by_email as (
    select members.member_id, count(distinct customers.person_id) as candidates, min(customers.person_id) as person_id
    from members
    inner join customers on customers.email_normalized = members.email_normalized
    group by members.member_id
),

by_phone as (
    select members.member_id, count(distinct customers.person_id) as candidates, min(customers.person_id) as person_id
    from members
    inner join customers
        on customers.phone_normalized = members.phone_normalized
        and customers.last_name_normalized = members.last_name_normalized
    group by members.member_id
),

by_name_and_postal_code as (
    select members.member_id, count(distinct customers.person_id) as candidates, min(customers.person_id) as person_id
    from members
    inner join customers
        on customers.first_name_normalized = members.first_name_normalized
        and customers.last_name_normalized = members.last_name_normalized
        and customers.postal_code = members.postal_code
    group by members.member_id
)

select
    members.member_id,
    case
        when by_email.candidates = 1 then by_email.person_id
        when by_email.member_id is null and by_phone.candidates = 1 then by_phone.person_id
        when by_email.member_id is null and by_phone.member_id is null and by_name.candidates = 1
            then by_name.person_id
    end as person_id,
    case
        when by_email.candidates = 1 and by_phone.candidates = 1 and by_phone.person_id = by_email.person_id
            then 'email_and_phone'
        when by_email.candidates = 1 then 'email'
        when by_email.candidates > 1 then 'ambiguous_email'
        when by_phone.candidates = 1 then 'phone_and_last_name'
        when by_phone.candidates > 1 then 'ambiguous_phone'
        when by_name.candidates = 1 then 'name_and_postal_code'
        when by_name.candidates > 1 then 'ambiguous_name'
        else 'no_match'
    end as match_method,
    coalesce(by_email.candidates, 0) as email_candidates,
    coalesce(by_phone.candidates, 0) as phone_candidates,
    coalesce(by_name.candidates, 0) as name_candidates,
    coalesce(by_email.candidates = 1 and by_phone.candidates >= 1 and by_phone.person_id <> by_email.person_id,
             false) as has_conflict
from members
left join by_email on by_email.member_id = members.member_id
left join by_phone on by_phone.member_id = members.member_id
left join by_name_and_postal_code as by_name on by_name.member_id = members.member_id
