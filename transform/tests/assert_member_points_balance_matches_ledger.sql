-- A member's points balance is the sum of their points transactions.
with ledger as (
    select member_id, sum(points) as points
    from {{ ref('stg_loyalty__points_transactions') }}
    group by member_id
)

select members.member_id, members.points_balance, coalesce(ledger.points, 0) as ledger_points
from {{ ref('stg_loyalty__members') }} as members
left join ledger on ledger.member_id = members.member_id
where members.points_balance <> coalesce(ledger.points, 0)
