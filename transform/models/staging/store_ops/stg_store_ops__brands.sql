select
    id as brand_id,
    name as brand_name,
    is_house_brand
from {{ source('store_ops', 'brands') }}
