select
    record:campaign_id::int as campaign_id,
    record:code::varchar as campaign_code,
    record:name::varchar as campaign_name,
    record:department::varchar as department_code,
    record:discount_percent::int as discount_percent,
    record:starts_on::date as starts_on,
    record:ends_on::date as ends_on,
    record:channel::varchar as channel
from {{ source('loyalty', 'campaigns') }}
qualify row_number() over (partition by record_id order by changed_at desc, _loaded_at desc) = 1
