-- Each campaign's naive lift (from campaign_performance) beside the generator's true effect (seed
-- campaign_true_lift: how many extra trips, relative to a member's normal rate, the campaign caused; 0.05 means it
-- did almost nothing). They are on different scales; the point is whether the naive measure ranks campaigns in the
-- right order and how often it calls a dud a success.
select
    performance.campaign_id,
    performance.campaign_code,
    performance.department_code,
    performance.discount_percent,
    performance.naive_lift,
    truth.true_lift,
    truth.true_lift < 0.1 as was_a_dud,
    performance.naive_lift > 0.05 as looks_successful,
    percent_rank() over (order by performance.naive_lift) as naive_rank,
    percent_rank() over (order by truth.true_lift) as true_rank
from {{ ref('campaign_performance') }} as performance
inner join {{ ref('campaign_true_lift') }} as truth on truth.campaign_id = performance.campaign_id
