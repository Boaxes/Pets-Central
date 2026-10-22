import streamlit as st

from data import query, titled

st.set_page_config(page_title='Customers and Loyalty', page_icon='🐾', layout='wide')
st.title('Customers and Loyalty')
st.caption('The store system and the loyalty vendor share no customer ID. dbt matches them by email, then by name and '
           'phone; duplicate customer records are merged into one person first.')

types = query('select customer_type, count(*) as people from marts.dim_customers group by 1 order by 2 desc')
people = int(types.people.sum())
buyers = types[types.customer_type != 'never purchased'].people.sum()
repeat = types[types.customer_type == 'repeat'].people.sum()
members = query('''
    select count(*) as members,
           sum(case when customer_records > 1 then 1 else 0 end) as merged
    from marts.dim_customers
    where is_loyalty_member
''').iloc[0]
merged = query('select sum(customer_records - 1) as extra_records from marts.dim_customers').iloc[0]

cols = st.columns(4)
cols[0].metric('People', f'{people:,}')
cols[1].metric('Repeat Rate', f'{repeat / buyers:.1%}', help='Buyers who came back at least once')
cols[2].metric('Matched Loyalty Members', f'{members.members:,.0f}')
cols[3].metric('Duplicate Records Merged', f'{merged.extra_records:,.0f}')

left, right = st.columns(2)
left.subheader('Customer Types')
left.bar_chart(titled(types), x='Customer Type', y='People')
right.subheader('How Members Were Matched')
methods = query('''
    select loyalty_match_method as method, count(*) as members
    from marts.dim_customers
    where is_loyalty_member
    group by 1 order by 2 desc
''')
right.bar_chart(titled(methods), x='Method', y='Members')

st.subheader('Members Against Non-Members')
st.caption('People who bought at least once.')
compare = query('''
    select case when is_loyalty_member then 'Member' else 'Not a member' end as "group",
           count(*) as people,
           avg(purchases)::float as purchases_each,
           avg(lifetime_net_amount)::float as spend_each,
           avg(case when customer_type = 'repeat' then 1.0 else 0.0 end)::float as repeat_rate
    from marts.dim_customers
    where customer_type <> 'never purchased'
    group by 1 order by 1
''')
st.dataframe(titled(compare), hide_index=True, use_container_width=True,
             column_config={'Spend Each': st.column_config.NumberColumn(format='$%.2f'),
                            'Purchases Each': st.column_config.NumberColumn(format='%.2f'),
                            'Repeat Rate': st.column_config.NumberColumn(format='%.3f')})

st.subheader('Loyalty Tiers')
tiers = query('''
    select loyalty_tier as tier, count(*) as members, avg(points_balance)::float as average_points
    from marts.dim_customers
    where is_loyalty_member
    group by 1 order by 2 desc
''')
st.bar_chart(titled(tiers), x='Tier', y='Members')
