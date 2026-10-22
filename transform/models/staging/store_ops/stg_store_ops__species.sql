select
    id as species_id,
    department_id,
    common_name,
    nullif(scientific_name, '') as scientific_name
from {{ source('store_ops', 'species') }}
