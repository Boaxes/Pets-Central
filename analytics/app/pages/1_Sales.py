import pandas as pd
import streamlit as st

from data import query, quoted, titled

st.set_page_config(page_title='Sales', page_icon='🐾', layout='wide')
st.title('Sales')

years = query('select distinct extract(year from sale_date) as year from marts.fct_sales order by 1 desc').year
regions = query('select distinct region_name from marts.dim_stores order by 1').region_name

left, right = st.columns(2)
year = int(left.selectbox('Year', [int(y) for y in years]))
region = right.selectbox('Region', ['All regions', *regions])

where = f'not lines.is_cancelled and extract(year from lines.sale_date) = {year}'
if region != 'All regions':
    where += f' and stores.region_name = {quoted(region)}'
lines = f'''
    from marts.fct_sale_lines as lines
    inner join marts.dim_stores as stores on stores.store_id = lines.store_id
    inner join marts.dim_products as products on products.product_id = lines.product_id
    where {where}
'''

totals = query(f'''
    select count(distinct lines.sale_id) as sales,
           sum(lines.net_amount)::float as revenue,
           sum(lines.gross_margin)::float as margin,
           sum(lines.quantity)::float as item_count
    {lines}
''').iloc[0]
cols = st.columns(4)
cols[0].metric('Revenue', f'${(totals.revenue or 0) / 1e6:,.2f}M')
cols[1].metric('Sales', f'{totals.sales:,.0f}')
cols[2].metric('Gross Margin', f'{(totals.margin or 0) / (totals.revenue or 1):.1%}')
cols[3].metric('Items Sold', f'{totals.item_count or 0:,.0f}')

st.subheader('By Month')
monthly = titled(query(f'''
    select date_trunc('month', lines.sale_date) as month, sum(lines.net_amount)::float as revenue
    {lines}
    group by 1 order by 1
'''))
monthly['Month'] = pd.to_datetime(monthly['Month']).dt.strftime('%b')  # one year: bars labeled by month
st.bar_chart(monthly, x='Month', y='Revenue', sort=False)

left, right = st.columns(2)
left.subheader('By Department')
departments = titled(query(f'''
    select products.department_name as department, sum(lines.net_amount)::float as revenue
    {lines}
    group by 1 order by 2 desc
'''))
left.bar_chart(departments, x='Department', y='Revenue')
right.subheader('By Region' if region == 'All regions' else 'By Store Format')
group = 'stores.region_name' if region == 'All regions' else 'stores.store_format'
split = titled(query(f'''
    select {group} as name, sum(lines.net_amount)::float as revenue
    {lines}
    group by 1 order by 2 desc
'''))
right.bar_chart(split, x='Name', y='Revenue')

st.subheader('Top 20 Stores')
stores = titled(query(f'''
    select stores.store_code as store, stores.store_name as name, stores.city, stores.state,
           count(distinct lines.sale_id) as sales,
           sum(lines.net_amount)::float as revenue,
           sum(lines.gross_margin)::float / nullif(sum(lines.net_amount), 0)::float as margin_rate
    {lines}
    group by 1, 2, 3, 4 order by 6 desc limit 20
'''))
st.dataframe(stores, hide_index=True, use_container_width=True,
             column_config={'Revenue': st.column_config.NumberColumn(format='$%.0f'),
                            'Margin Rate': st.column_config.NumberColumn(format='%.3f')})
