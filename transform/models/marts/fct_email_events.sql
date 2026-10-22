-- One row per campaign email sent to a member.
select
    emails.email_event_id,
    emails.campaign_id,
    emails.member_id,
    matches.person_id,
    emails.sent_at_utc,
    emails.sent_at_utc::date as sent_date,
    emails.was_opened,
    emails.was_clicked,
    emails.opened_at_utc,
    emails.clicked_at_utc,
    datediff('minute', emails.sent_at_utc, emails.opened_at_utc) as minutes_to_open,
    emails.unsubscribed,
    emails.recorded_at_utc
from {{ ref('stg_loyalty__email_events') }} as emails
left join {{ ref('int_member_matches') }} as matches on matches.member_id = emails.member_id
