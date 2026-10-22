-- At most one loyalty membership per person. A person matched by several members keeps their active,
-- most recently enrolled one.
select
    matches.person_id,
    members.member_id,
    members.tier,
    members.status,
    members.email_opt_in,
    members.pet_types,
    members.enrolled_at_utc,
    members.points_balance,
    matches.match_method,
    count(*) over (partition by matches.person_id) as memberships_matched
from {{ ref('int_member_matches') }} as matches
inner join {{ ref('stg_loyalty__members') }} as members on members.member_id = matches.member_id
where matches.person_id is not null
qualify row_number() over (
    partition by matches.person_id order by members.status = 'active' desc, members.enrolled_at_utc desc
) = 1
