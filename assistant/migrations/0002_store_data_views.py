"""The store_data schema: what the Store Assistant's database login can see.

Every view shows one store's data: the store bound to the current database session in assistant_scope. The views
run with their owner's rights, so the assistant's login needs no access to the tables underneath, and it can't read
assistant_scope to pick a different store. Catalog data (products and prices) is the same for every store.
"""

from django.db import migrations

from assistant.grants import grant_read_access

THIS_STORE = '(SELECT store_id FROM assistant_scope WHERE backend_pid = pg_backend_pid())'

VIEWS = f"""
CREATE SCHEMA store_data;

CREATE VIEW store_data.store WITH (security_barrier) AS
SELECT s.store_code, s.name, r.name AS region, s.original_chain, s.store_format, s.address_line, s.city, s.state,
       s.postal_code, s.time_zone, s.opened_on, s.acquired_on, s.closed_on
FROM stores_store s
JOIN stores_region r ON r.id = s.region_id
WHERE s.id = {THIS_STORE};

CREATE VIEW store_data.employees WITH (security_barrier) AS
SELECT e.id AS employee_id, e.employee_number, e.first_name, e.last_name, e.role, e.hourly_rate, e.hired_on,
       e.terminated_on, e.terminated_on IS NULL AS is_active
FROM stores_employee e
WHERE e.store_id = {THIS_STORE};

CREATE VIEW store_data.customers WITH (security_barrier) AS
SELECT c.id AS customer_id, c.first_name, c.last_name, c.email, c.phone, c.postal_code, c.marketing_opt_in,
       c.created_at
FROM customers_customer c
WHERE c.home_store_id = {THIS_STORE};

CREATE VIEW store_data.products WITH (security_barrier) AS
SELECT p.id AS product_id, p.sku, p.name, d.name AS department, c.name AS category, b.name AS brand,
       coalesce(b.is_house_brand, false) AS is_house_brand, sp.common_name AS species,
       p.species_id IS NOT NULL AS is_live_animal, p.introduced_on, p.discontinued_on,
       pr.list_price, pr.unit_cost, sl.quantity_on_hand, sl.reorder_point
FROM catalog_product p
JOIN catalog_category c ON c.id = p.category_id
JOIN catalog_department d ON d.id = c.department_id
LEFT JOIN catalog_brand b ON b.id = p.brand_id
LEFT JOIN catalog_species sp ON sp.id = p.species_id
LEFT JOIN catalog_productprice pr ON pr.product_id = p.id AND pr.valid_to IS NULL
LEFT JOIN inventory_stocklevel sl ON sl.product_id = p.id AND sl.store_id = {THIS_STORE};

CREATE VIEW store_data.animals WITH (security_barrier) AS
SELECT a.id AS animal_id, a.product_id, sp.common_name AS species, nullif(a.name, '') AS name, a.sex, a.born_on,
       a.received_on,
       CASE WHEN l.id IS NOT NULL THEN 'sold' WHEN a.removed_on IS NOT NULL THEN 'removed' ELSE 'available' END
           AS status,
       l.sale_id, s.sold_at, a.removed_on, nullif(a.removal_reason, '') AS removal_reason
FROM inventory_animal a
JOIN catalog_product p ON p.id = a.product_id
JOIN catalog_species sp ON sp.id = p.species_id
LEFT JOIN sales_saleline l ON l.animal_id = a.id
LEFT JOIN sales_sale s ON s.id = l.sale_id
WHERE a.store_id = {THIS_STORE};

CREATE VIEW store_data.animal_caretakers WITH (security_barrier) AS
SELECT ac.animal_id, ac.employee_id
FROM inventory_animal_caretakers ac
JOIN inventory_animal a ON a.id = ac.animal_id
WHERE a.store_id = {THIS_STORE};

CREATE VIEW store_data.sales WITH (security_barrier) AS
SELECT s.id AS sale_id, s.receipt_number, s.sold_at, s.channel, s.status, s.cancelled_at, s.customer_id,
       s.employee_id, nullif(s.coupon_code, '') AS coupon_code,
       coalesce(t.net_total, 0) AS net_total, coalesce(t.item_count, 0) AS item_count
FROM sales_sale s
LEFT JOIN LATERAL (
    SELECT sum(l.quantity * l.unit_price - l.discount_amount) AS net_total, sum(l.quantity) AS item_count
    FROM sales_saleline l
    WHERE l.sale_id = s.id
) t ON true
WHERE s.store_id = {THIS_STORE};

CREATE VIEW store_data.sale_lines WITH (security_barrier) AS
SELECT l.id AS sale_line_id, l.sale_id, l.line_number, s.sold_at, s.status AS sale_status, l.product_id, p.sku,
       p.name AS product_name, d.name AS department, c.name AS category, l.animal_id, l.quantity, l.unit_price,
       l.unit_cost, l.discount_amount, l.quantity * l.unit_price - l.discount_amount AS net_amount
FROM sales_saleline l
JOIN sales_sale s ON s.id = l.sale_id
JOIN catalog_product p ON p.id = l.product_id
JOIN catalog_category c ON c.id = p.category_id
JOIN catalog_department d ON d.id = c.department_id
WHERE s.store_id = {THIS_STORE};

CREATE VIEW store_data.returns WITH (security_barrier) AS
SELECT r.id AS return_id, r.return_number, r.sale_id, r.returned_at, r.reason, r.employee_id,
       s.store_id = r.store_id AS sold_here,
       coalesce(t.refund_total, 0) AS refund_total, coalesce(t.item_count, 0) AS item_count
FROM sales_salereturn r
JOIN sales_sale s ON s.id = r.sale_id
LEFT JOIN LATERAL (
    SELECT sum(rl.refund_amount) AS refund_total, sum(rl.quantity) AS item_count
    FROM sales_salereturnline rl
    WHERE rl.sale_return_id = r.id
) t ON true
WHERE r.store_id = {THIS_STORE};

CREATE VIEW store_data.return_lines WITH (security_barrier) AS
SELECT rl.sale_return_id AS return_id, rl.sale_line_id, l.product_id, p.sku, p.name AS product_name, rl.quantity,
       rl.refund_amount, rl.restocked
FROM sales_salereturnline rl
JOIN sales_salereturn r ON r.id = rl.sale_return_id
JOIN sales_saleline l ON l.id = rl.sale_line_id
JOIN catalog_product p ON p.id = l.product_id
WHERE r.store_id = {THIS_STORE};
"""


def grant_to_assistant(apps, schema_editor):
    grant_read_access(schema_editor.connection)


class Migration(migrations.Migration):
    dependencies = [
        ('assistant', '0001_initial'),
        ('stores', '0001_initial'),
        ('catalog', '0001_initial'),
        ('customers', '0001_initial'),
        ('inventory', '0001_initial'),
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(VIEWS, reverse_sql='DROP SCHEMA store_data CASCADE;'),
        migrations.RunPython(grant_to_assistant, migrations.RunPython.noop),
    ]
