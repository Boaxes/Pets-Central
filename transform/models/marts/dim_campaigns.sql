select
    campaigns.campaign_id,
    campaigns.campaign_code,
    campaigns.campaign_name,
    campaigns.department_code,
    departments.department_name,
    campaigns.discount_percent,
    campaigns.starts_on,
    campaigns.ends_on,
    datediff('day', campaigns.starts_on, campaigns.ends_on) + 1 as days_running,
    campaigns.channel
from {{ ref('stg_loyalty__campaigns') }} as campaigns
left join {{ ref('stg_store_ops__departments') }} as departments
    on departments.department_code = campaigns.department_code
