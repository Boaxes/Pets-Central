select
    points.points_transaction_id,
    points.member_id,
    matches.person_id,
    points.transaction_type,
    points.points,
    points.purchase_amount,
    stores.store_id,
    points.occurred_at_utc,
    points.occurred_at_local::date as occurred_date,
    points.recorded_at_utc,
    points.days_to_record,
    points.days_to_record > 1 as arrived_late
from {{ ref('stg_loyalty__points_transactions') }} as points
left join {{ ref('int_member_matches') }} as matches on matches.member_id = points.member_id
left join {{ ref('stg_store_ops__stores') }} as stores on stores.store_code = points.store_code
