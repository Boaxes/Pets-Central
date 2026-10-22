-- occurred_at arrives in the store's local time with no offset. It is converted to UTC using the store's time zone.
with transactions as (
    select
        record:transaction_id::int as points_transaction_id,
        record:member_id::varchar as member_id,
        record:type::varchar as transaction_type,
        record:points::int as points,
        record:purchase_amount::number(12, 2) as purchase_amount,
        record:store_code::varchar as store_code_loyalty,
        {{ store_code_from_loyalty('record:store_code::varchar') }} as store_code,
        record:occurred_at::timestamp_ntz as occurred_at_local,
        {{ to_utc('changed_at') }} as recorded_at_utc
    from {{ source('loyalty', 'points_transactions') }}
    qualify row_number() over (partition by record_id order by changed_at desc, _loaded_at desc) = 1
)

select
    transactions.*,
    convert_timezone(stores.time_zone, 'UTC', transactions.occurred_at_local) as occurred_at_utc,
    datediff('minute', convert_timezone(stores.time_zone, 'UTC', transactions.occurred_at_local),
             transactions.recorded_at_utc) / 1440.0 as days_to_record
from transactions
left join {{ ref('stg_store_ops__stores') }} as stores
    on stores.store_code = transactions.store_code
