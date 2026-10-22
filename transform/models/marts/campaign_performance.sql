-- One row per campaign: how the emails did, how the coupon was used, and how the targeted department sold while
-- it ran compared with the same number of days just before.
--
-- naive_lift compares the department's daily sales during the campaign with the days before it. It ignores
-- seasonality and other campaigns, so it is a rough signal, not the campaign's true effect.
with campaigns as (
    select * from {{ ref('dim_campaigns') }}
),

emails as (
    select
        campaign_id,
        count(*) as emails_sent,
        count_if(was_opened) as emails_opened,
        count_if(was_clicked) as emails_clicked,
        count_if(unsubscribed) as unsubscribes
    from {{ ref('fct_email_events') }}
    group by campaign_id
),

redemptions as (
    select
        campaign_id,
        count_if(not is_voided) as redemptions,
        count_if(is_voided) as voided_redemptions,
        count_if(not is_voided and by_member) as member_redemptions,
        sum(iff(is_voided, 0, order_total)) as redeemed_order_total,
        sum(iff(is_voided, 0, discount_amount)) as discount_given
    from {{ ref('fct_coupon_redemptions') }}
    group by campaign_id
),

department_daily as (
    select lines.sale_date, products.department_code, sum(lines.net_amount) as net_amount
    from {{ ref('fct_sale_lines') }} as lines
    inner join {{ ref('dim_products') }} as products on products.product_id = lines.product_id
    where not lines.is_cancelled
    group by lines.sale_date, products.department_code
),

windows as (
    select
        campaigns.campaign_id,
        sum(iff(daily.sale_date between campaigns.starts_on and campaigns.ends_on, daily.net_amount, 0))
            / campaigns.days_running as daily_net_during,
        sum(iff(daily.sale_date < campaigns.starts_on, daily.net_amount, 0))
            / campaigns.days_running as daily_net_before
    from campaigns
    inner join department_daily as daily
        on daily.department_code = campaigns.department_code
        and daily.sale_date between dateadd('day', -campaigns.days_running, campaigns.starts_on) and campaigns.ends_on
    group by campaigns.campaign_id, campaigns.days_running
)

select
    campaigns.*,
    coalesce(emails.emails_sent, 0) as emails_sent,
    coalesce(emails.emails_opened, 0) as emails_opened,
    coalesce(emails.emails_clicked, 0) as emails_clicked,
    coalesce(emails.unsubscribes, 0) as unsubscribes,
    round(emails.emails_opened / nullif(emails.emails_sent, 0), 4) as open_rate,
    round(emails.emails_clicked / nullif(emails.emails_sent, 0), 4) as click_rate,
    coalesce(redemptions.redemptions, 0) as redemptions,
    coalesce(redemptions.voided_redemptions, 0) as voided_redemptions,
    coalesce(redemptions.member_redemptions, 0) as member_redemptions,
    coalesce(redemptions.redeemed_order_total, 0) as redeemed_order_total,
    coalesce(redemptions.discount_given, 0) as discount_given,
    round(windows.daily_net_during, 2) as department_daily_net_during,
    round(windows.daily_net_before, 2) as department_daily_net_before,
    round(windows.daily_net_during / nullif(windows.daily_net_before, 0) - 1, 4) as naive_lift
from campaigns
left join emails on emails.campaign_id = campaigns.campaign_id
left join redemptions on redemptions.campaign_id = campaigns.campaign_id
left join windows on windows.campaign_id = campaigns.campaign_id
