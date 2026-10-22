-- The v2 member record, with contact details normalized the same way as store customers' so they can be matched.
select
    record:member_id::varchar as member_id,
    record:first_name::varchar as first_name,
    record:last_name::varchar as last_name,
    record:email::varchar as email_as_recorded,
    {{ normalize_email('record:email::varchar') }} as email_normalized,
    {{ normalize_phone('record:phone_e164::varchar') }} as phone_normalized,
    {{ normalize_name('record:first_name::varchar') }} as first_name_normalized,
    {{ normalize_name('record:last_name::varchar') }} as last_name_normalized,
    record:postal_code::varchar as postal_code,
    record:home_store::varchar as home_store_code_loyalty,
    {{ store_code_from_loyalty('record:home_store::varchar') }} as home_store_code,
    array_to_string(record:pet_types, ',') as pet_types,
    record:email_opt_in::boolean as email_opt_in,
    record:tier::varchar as tier,
    record:status::varchar as status,
    {{ to_utc('record:enrolled_at::timestamp_tz') }} as enrolled_at_utc,
    {{ to_utc('record:closed_at::timestamp_tz') }} as closed_at_utc,
    record:points_balance::int as points_balance,
    {{ to_utc('changed_at') }} as updated_at_utc
from {{ source('loyalty', 'members') }}
-- RAW keeps every version the API returned; use the latest.
qualify row_number() over (partition by record_id order by changed_at desc, _loaded_at desc) = 1
