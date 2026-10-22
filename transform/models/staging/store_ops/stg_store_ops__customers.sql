-- Customer records as staff entered them, with normalized copies of the contact details for matching.
select
    id as customer_id,
    first_name,
    last_name,
    nullif(email, '') as email_as_typed,
    nullif(phone, '') as phone_as_typed,
    {{ normalize_email('email') }} as email_normalized,
    {{ normalize_phone('phone') }} as phone_normalized,
    {{ normalize_name('first_name') }} as first_name_normalized,
    {{ normalize_name('last_name') }} as last_name_normalized,
    nullif(postal_code, '') as postal_code,
    home_store_id,
    marketing_opt_in,
    {{ to_utc('created_at') }} as created_at_utc,
    {{ to_utc('updated_at') }} as updated_at_utc
from {{ source('store_ops', 'customers') }}
qualify row_number() over (partition by id order by updated_at desc, _loaded_at desc) = 1
