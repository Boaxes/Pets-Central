with days as (
    {{ dbt_utils.date_spine(datepart='day', start_date="'2015-01-01'::date", end_date="'2028-01-01'::date") }}
)

select
    date_day,
    year(date_day) as year,
    quarter(date_day) as quarter,
    month(date_day) as month,
    monthname(date_day) as month_name,
    date_trunc('month', date_day) as month_start,
    weekofyear(date_day) as iso_week,
    dayofweekiso(date_day) as day_of_week,
    dayname(date_day) as day_name,
    dayofweekiso(date_day) >= 6 as is_weekend
from days
