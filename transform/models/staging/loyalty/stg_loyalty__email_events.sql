select
    record:event_id::int as email_event_id,
    record:campaign_id::int as campaign_id,
    record:member_id::varchar as member_id,
    {{ to_utc('record:sent_at::timestamp_tz') }} as sent_at_utc,
    {{ to_utc('record:opened_at::timestamp_tz') }} as opened_at_utc,
    {{ to_utc('record:clicked_at::timestamp_tz') }} as clicked_at_utc,
    record:opened_at::timestamp_tz is not null as was_opened,
    record:clicked_at::timestamp_tz is not null as was_clicked,
    record:unsubscribed::boolean as unsubscribed,
    {{ to_utc('changed_at') }} as recorded_at_utc
from {{ source('loyalty', 'email_events') }}
qualify row_number() over (partition by record_id order by changed_at desc, _loaded_at desc) = 1
