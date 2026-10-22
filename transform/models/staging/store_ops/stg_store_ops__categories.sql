select
    id as category_id,
    department_id,
    name as category_name,
    startswith(name, 'Live') as is_live_category
from {{ source('store_ops', 'categories') }}
