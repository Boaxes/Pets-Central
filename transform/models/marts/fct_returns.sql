-- One row per returned line. A return can happen at a different store from the sale.
select
    return_lines.return_line_id,
    returns.return_id,
    returns.return_number,
    returns.returned_at_utc,
    convert_timezone('UTC', return_stores.time_zone, returns.returned_at_utc)::date as return_date,
    returns.store_id as return_store_id,
    sale_lines.store_id as sale_store_id,
    returns.store_id <> sale_lines.store_id as returned_elsewhere,
    returns.sale_id,
    return_lines.sale_line_id,
    sale_lines.product_id,
    sale_lines.person_id,
    returns.employee_id,
    returns.reason,
    return_lines.quantity,
    return_lines.refund_amount,
    return_lines.restocked,
    datediff('day', sale_lines.sold_at_utc, returns.returned_at_utc) as days_to_return
from {{ ref('stg_store_ops__return_lines') }} as return_lines
inner join {{ ref('stg_store_ops__returns') }} as returns on returns.return_id = return_lines.return_id
inner join {{ ref('fct_sale_lines') }} as sale_lines on sale_lines.sale_line_id = return_lines.sale_line_id
inner join {{ ref('stg_store_ops__stores') }} as return_stores on return_stores.store_id = returns.store_id
