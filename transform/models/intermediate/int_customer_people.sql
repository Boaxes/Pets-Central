-- Which customer records are the same person.
--
-- Two records are the same person when they share a normalized email or phone, directly or through another
-- record (A shares an email with B, and B shares a phone with C). These groups are the connected components of a
-- graph whose edges are shared contact details, found here by label propagation: every record starts labeled
-- with its own id, then repeatedly takes the smallest label among the records it shares an email or phone with.
-- People have only a few records, so a handful of rounds settles every group; the test
-- assert_customer_people_converged fails if one more round would still change something.
--
-- person_id is the smallest customer_id in the group, so it is stable as long as that record exists.

{% set rounds = 6 %}

with customers as (
    select customer_id, email_normalized, phone_normalized
    from {{ ref('stg_store_ops__customers') }}
),

match_keys as (
    select customer_id, 'email:' || email_normalized as match_key from customers where email_normalized is not null
    union all
    select customer_id, 'phone:' || phone_normalized from customers where phone_normalized is not null
),

labels_0 as (
    select customer_id, customer_id as label from customers
),

{% for round in range(rounds) %}
key_labels_{{ round }} as (
    select match_keys.match_key, min(labels.label) as label
    from match_keys
    inner join labels_{{ round }} as labels on labels.customer_id = match_keys.customer_id
    group by match_keys.match_key
),

labels_{{ round + 1 }} as (
    select labels.customer_id, least(labels.label, coalesce(min(key_labels.label), labels.label)) as label
    from labels_{{ round }} as labels
    left join match_keys on match_keys.customer_id = labels.customer_id
    left join key_labels_{{ round }} as key_labels on key_labels.match_key = match_keys.match_key
    group by labels.customer_id, labels.label
),
{% endfor %}

people as (
    select customer_id, label as person_id
    from labels_{{ rounds }}
)

select
    customer_id,
    person_id,
    count(*) over (partition by person_id) as records_for_person
from people
