import streamlit as st

from data import query, titled

st.set_page_config(page_title='Campaigns', page_icon='🐾', layout='wide')
st.title('Campaigns')
st.caption('Naive lift compares the department\'s daily sales during a campaign with the same number of days just '
           'before it. It credits the campaign with everything else that changed: seasons, holidays, other '
           'campaigns, new stores.')

campaigns = query('''
    select campaign_id, campaign_name, department_name, channel, discount_percent, starts_on, ends_on,
           emails_sent, open_rate::float as open_rate, click_rate::float as click_rate,
           redemptions, discount_given::float as discount_given, naive_lift::float as naive_lift
    from marts.campaign_performance
    order by starts_on
''')

# The true lift comes from the data generator's truth files, which exist only where the data was generated (the
# stand-in's local run). Production's warehouse never had them.
try:
    truth = query('''
        select campaign_id, true_lift::float as true_lift, was_a_dud, looks_successful
        from evaluation.campaign_lift_check
    ''')
    campaigns = campaigns.merge(truth, on='campaign_id', how='left')
except Exception:
    truth = None

cols = st.columns(4)
cols[0].metric('Campaigns', f'{len(campaigns):,}')
cols[1].metric('Emails Sent', f'{campaigns.emails_sent.sum():,.0f}')
cols[2].metric('Coupons Redeemed', f'{campaigns.redemptions.sum():,.0f}')
cols[3].metric('Discount Given', f'${campaigns.discount_given.sum():,.0f}')

if truth is not None:
    st.subheader('Naive Lift Against True Lift')
    duds = campaigns[campaigns.was_a_dud.astype(bool)]
    fooled = int(duds.looks_successful.astype(bool).sum())
    st.caption('Each dot is a campaign. True lift is the extra trips the campaign really caused, from the data '
               'generator; it is on a different scale from naive lift, so what matters is whether the two rank '
               f'campaigns the same way. Of {len(duds)} campaigns that did almost nothing, naive lift calls '
               f'{fooled} a success.')
    st.scatter_chart(titled(campaigns), x='True Lift', y='Naive Lift')
else:
    st.info('True lift is only known where the data was generated, so it is shown in the demo, not here.')

st.subheader('Every Campaign')
table = campaigns.drop(columns=[c for c in ['campaign_id', 'was_a_dud', 'looks_successful'] if c in campaigns])
st.dataframe(titled(table), hide_index=True, use_container_width=True,
             column_config={'Open Rate': st.column_config.NumberColumn(format='%.3f'),
                            'Click Rate': st.column_config.NumberColumn(format='%.3f'),
                            'Discount Given': st.column_config.NumberColumn(format='$%.0f'),
                            'Naive Lift': st.column_config.NumberColumn(format='%.3f'),
                            'True Lift': st.column_config.NumberColumn(format='%.3f')})
