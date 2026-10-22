select
    id as department_id,
    code as department_code,
    name as department_name
from {{ source('store_ops', 'departments') }}
