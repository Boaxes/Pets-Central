select
    id as product_id,
    sku,
    name as product_name,
    category_id,
    brand_id,
    species_id,
    species_id is not null as is_live_animal,
    introduced_on,
    discontinued_on
from {{ source('store_ops', 'products') }}
