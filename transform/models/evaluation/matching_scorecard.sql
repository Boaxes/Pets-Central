-- How well the matching did, scored against the generator's truth file (seed loyalty_member_truth), which says
-- which customer records really belong to each loyalty member. The truth never feeds the matching itself.
--
-- precision: of the members matched to a person, the share matched to the right one.
-- recall: of the members who really are store customers, the share matched to the right person.
-- duplicates merged: of the people with two customer records, the share whose records became one person.

with truth as (
    select distinct truth.member_id, people.person_id
    from {{ ref('loyalty_member_truth') }} as truth
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = truth.customer_id
),

truth_members as (
    select member_id, count(distinct person_id) as true_people
    from truth
    group by member_id
),

scored as (
    select
        matches.member_id,
        matches.match_method,
        matches.person_id is not null as is_matched,
        truth_members.member_id is not null as is_customer,
        truth.person_id is not null as is_correct
    from {{ ref('int_member_matches') }} as matches
    left join truth_members on truth_members.member_id = matches.member_id
    left join truth on truth.member_id = matches.member_id and truth.person_id = matches.person_id
),

duplicate_records as (
    select truth.member_id, count(distinct people.person_id) as people
    from {{ ref('loyalty_member_truth') }} as truth
    inner join {{ ref('int_customer_people') }} as people on people.customer_id = truth.customer_id
    group by truth.member_id
    having count(distinct truth.customer_id) > 1
),

by_method as (
    select
        match_method as scope,
        count(*) as members,
        count_if(is_matched) as matched,
        count_if(is_correct) as correct,
        count_if(is_customer) as really_customers
    from scored
    group by match_method
),

overall as (
    select
        'all members' as scope,
        count(*) as members,
        count_if(is_matched) as matched,
        count_if(is_correct) as correct,
        count_if(is_customer) as really_customers
    from scored
)

select
    scope,
    members,
    matched,
    correct,
    really_customers,
    round(correct / nullif(matched, 0), 4) as precision,
    round(correct / nullif(really_customers, 0), 4) as recall,
    (select round(count_if(people = 1) / nullif(count(*), 0), 4) from duplicate_records) as duplicates_merged
from (select * from overall union all select * from by_method)
order by scope = 'all members' desc, members desc
