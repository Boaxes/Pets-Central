"""Pets Central Analytics: a read-only view of the warehouse's marts. This page is the overview; the others are in
pages/. Runs in Streamlit in Snowflake (with Cortex Analyst) and, as the demo, on Streamlit Community Cloud (with
Claude)."""

import streamlit as st

from data import query, titled

st.set_page_config(page_title='Pets Central Analytics', page_icon='🐾', layout='wide')

st.title('Pets Central Analytics')
st.caption('A national pet store chain, as its data warehouse sees it. Cancelled sales are left out everywhere.')

totals = query('''
    select count(*) as sales,
           sum(net_amount)::float as revenue,
           sum(gross_margin)::float as margin,
           count(distinct store_id) as stores,
           min(sale_date) as first_day,
           max(sale_date) as last_day
    from marts.fct_sales
    where not is_cancelled
''').iloc[0]

cols = st.columns(5)
cols[0].metric('Revenue', f'${totals.revenue / 1e6:,.1f}M')
cols[1].metric('Sales', f'{totals.sales:,.0f}')
cols[2].metric('Gross Margin', f'{totals.margin / totals.revenue:.1%}')
cols[3].metric('Average Sale', f'${totals.revenue / totals.sales:,.2f}')
cols[4].metric('Stores', f'{totals.stores:,.0f}')
st.caption(f'From {totals.first_day} to {totals.last_day}.')

monthly = titled(query('''
    select date_trunc('month', sale_date) as month,
           sum(net_amount)::float as revenue,
           sum(gross_margin)::float as gross_margin
    from marts.fct_sales
    where not is_cancelled
    group by 1
    order by 1
'''))
st.subheader('Revenue by Month')
st.line_chart(monthly, x='Month', y=['Revenue', 'Gross Margin'])

left, right = st.columns(2)
left.subheader('Revenue by Channel')
channels = titled(query('''
    select channel, sum(net_amount)::float as revenue
    from marts.fct_sales
    where not is_cancelled
    group by 1
    order by 2 desc
'''))
left.bar_chart(channels, x='Channel', y='Revenue')
right.subheader('Who Buys')
buyers = titled(query('''
    select case when is_guest then 'Guest' when is_member then 'Loyalty member' else 'Known customer' end as buyer,
           sum(net_amount)::float as revenue
    from marts.fct_sales
    where not is_cancelled
    group by 1
    order by 2 desc
'''))
right.bar_chart(buyers, x='Buyer', y='Revenue')
