select
    products.product_id,
    products.sku,
    products.product_name,
    categories.category_name,
    departments.department_code,
    departments.department_name,
    brands.brand_name,
    coalesce(brands.is_house_brand, false) as is_house_brand,
    products.is_live_animal,
    species.common_name as species_common_name,
    species.scientific_name as species_scientific_name,
    products.introduced_on,
    products.discontinued_on,
    products.discontinued_on is null as is_active,
    prices.list_price as current_list_price,
    prices.unit_cost as current_unit_cost,
    round((prices.list_price - prices.unit_cost) / nullif(prices.list_price, 0), 4) as current_margin_rate
from {{ ref('stg_store_ops__products') }} as products
inner join {{ ref('stg_store_ops__categories') }} as categories on categories.category_id = products.category_id
inner join {{ ref('stg_store_ops__departments') }} as departments on departments.department_id = categories.department_id
left join {{ ref('stg_store_ops__brands') }} as brands on brands.brand_id = products.brand_id
left join {{ ref('stg_store_ops__species') }} as species on species.species_id = products.species_id
left join {{ ref('stg_store_ops__product_prices') }} as prices
    on prices.product_id = products.product_id and prices.is_current
