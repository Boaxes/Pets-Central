select
    id as region_id,
    code as region_code,
    name as region_name
from {{ source('store_ops', 'regions') }}
