-- Discounts never exceed the line, and nothing is negative, after loading and cleaning.
select sale_line_id
from {{ ref('fct_sale_lines') }}
where discount_amount < 0
   or discount_amount > gross_amount
   or quantity <= 0
   or unit_price < 0
   or unit_cost < 0
