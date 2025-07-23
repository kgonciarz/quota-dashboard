import streamlit as st
import pandas as pd
from supabase import create_client, Client
import altair as alt
import sys

# Use Streamlit Secrets for Supabase credentials in a production environment
# Ensure you have created a .streamlit/secrets.toml file with your credentials
# For local testing, you might keep the placeholders or use environment variables
SUPABASE_URL = None
SUPABASE_KEY = None
try:
    # Access secrets using .get() to avoid raising KeyError directly
    SUPABASE_URL = st.secrets.get("supabase", {}).get("url")
    SUPABASE_KEY = st.secrets.get("supabase", {}).get("key")

    # Check if secrets were successfully retrieved. If not, a KeyError will be raised.
    if not SUPABASE_URL or not SUPABASE_KEY:
         raise KeyError("Supabase secrets not found or incomplete in Streamlit Secrets.")

except KeyError:
    st.warning("Supabase credentials not found in Streamlit Secrets. Using placeholder values.")
    SUPABASE_URL = "https://your-project-id.supabase.co"
    SUPABASE_KEY = "YOUR_SUPABASE_KEY"
except Exception as e:
    st.error(f"An unexpected error occurred while accessing secrets: {e}")
    st.warning("Using placeholder values for Supabase credentials.")
    SUPABASE_URL = "https://your-project-id.supabase.co"
    SUPABASE_KEY = "YOUR_SUPABASE_KEY"


# Set up the Supabase client
supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "https://your-project-id.supabase.co": # Avoid connecting with placeholders
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        st.sidebar.success("Connected to Supabase.") # Add connection status to sidebar
    else:
        st.sidebar.warning("Using placeholder Supabase credentials. Connection skipped.")

except Exception as e:
    st.sidebar.error(f"Failed to connect to Supabase: {e}")


traceability_table_name = 'traceability'
farmers_table_name = 'farmers'

with st.spinner(f"Fetching data from {traceability_table_name} and {farmers_table_name}..."):
    # Get all relevant traceability records
    response_traceability = supabase.from_(traceability_table_name).select(
        'farmer_id, net_weight_kg, export_lot, exporter, cooperative_name, certification'
    ).execute()
    data_traceability = response_traceability.data

    # Get all farmers with quotas
    response_farmers = supabase.from_(farmers_table_name).select(
        'farmer_id, max_quota_kg'
    ).execute()
    data_farmers = response_farmers.data

if data_traceability and data_farmers:
    df_traceability = pd.DataFrame(data_traceability)
    df_farmers = pd.DataFrame(data_farmers)

    # Normalize farmer_id to match (trim + lowercase)
    df_traceability['farmer_id'] = df_traceability['farmer_id'].str.strip().str.lower()
    df_farmers['farmer_id'] = df_farmers['farmer_id'].str.strip().str.lower()

    # Remove nulls for aggregation
    df_traceability = df_traceability[df_traceability['net_weight_kg'].notnull()]
    df_farmers = df_farmers[df_farmers['max_quota_kg'].notnull()]

    # Aggregate traceability: sum net_weight, pick first exporter/cooperative/etc
    df_trace_summary = df_traceability.groupby('farmer_id').agg({
        'net_weight_kg': 'sum',
        'export_lot': 'first',
        'exporter': 'first',
        'cooperative_name': 'first',
        'certification': 'first'
    }).reset_index().rename(columns={'net_weight_kg': 'total_net_weight_kg'})

    # Merge with farmers
    df_combined = pd.merge(df_trace_summary, df_farmers, on='farmer_id', how='inner')

    # Calculate quota_used_pct
    df_combined['quota_used_pct'] = (df_combined['total_net_weight_kg'] / df_combined['max_quota_kg']) * 100

    # Classify quota status
    def classify_quota(pct):
        if pct <= 80:
            return 'OK'
        elif pct <= 100:
            return 'WARNING'
        else:
            return 'EXCEEDED'

    df_combined['quota_status'] = df_combined['quota_used_pct'].apply(classify_quota)

else:
    st.warning("No data fetched from Supabase or one of the datasets is empty.")
    df_combined = pd.DataFrame()



# Display a warning if no data matches the filters
if filtered_df.empty and (supabase and (data_quota or data_traceability)):
    # Only show this warning if data was fetched/attempted but filters resulted in empty
    st.warning("No data matches the selected filters.")


# Section for Key Metrics
st.header("Key Metrics") # Add section title
st.markdown("Summary statistics for the filtered data.") # Add descriptive text
with st.container():
    # Calculate key metrics from the filtered data
    total_farmers = filtered_df['farmer_id'].nunique() if 'farmer_id' in filtered_df.columns and not filtered_df.empty else 0
    average_quota_used_pct = filtered_df['quota_used_pct'].mean() if 'quota_used_pct' in filtered_df.columns and not filtered_df.empty else 0
    total_max_quota_kg = filtered_df['max_quota_kg'].sum() if 'max_quota_kg' in filtered_df.columns and not filtered_df.empty else 0
    total_net_weight_kg = filtered_df['total_net_weight_kg'].sum() if 'total_net_weight_kg' in filtered_df.columns and not filtered_df.empty else 0 # Use total_net_weight_kg from quota_view


    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.subheader("Total Farmers") # Add metric title
        st.metric(label="Total Farmers", value=total_farmers) # Use st.metric for better formatting and appearance
    with col2:
        st.subheader("Average Quota Used (%)") # Add metric title
        st.metric(label="Average Quota Used (%)", value=f"{average_quota_used_pct:.2f}%") # Format as percentage
    with col3:
        st.subheader("Total Max Quota (kg)") # Add metric title
        st.metric(label="Total Max Quota (kg)", value=f"{total_max_quota_kg:,.0f} kg") # Format with thousands separator and unit
    with col4:
        st.subheader("Total Net Weight (kg)") # Add metric title
        st.metric(label="Total Net Weight (kg)", value=f"{total_net_weight_kg:,.0f} kg") # Format with thousands separator and unit


# Section for Raw Data Table
st.header("Combined Data Table") # Add section title
st.markdown("Detailed farmer quota information.") # Add descriptive text
with st.container():
    if not filtered_df.empty:
        # Implement sorting for quota_used_pct - Move to main area for better visibility with the table
        sort_order = st.selectbox(
            "Sort the table by Quota Used (%)", # Add label for sorting control
            ["Ascending", "Descending"]
        )

        if sort_order == "Ascending":
            sorted_df = filtered_df.sort_values(by='quota_used_pct', ascending=True)
        else:
            sorted_df = filtered_df.sort_values(by='quota_used_pct', ascending=False)

        # Display the raw data table (only relevant columns) - Use st.dataframe with formatting
        st.dataframe(
            sorted_df[['farmer_id', 'max_quota_kg', 'total_net_weight_kg', 'quota_used_pct', 'quota_status', 'descriptive_quota_status', 'cooperative_name', 'certification', 'exporter', 'export_lot']].style
            .format({'quota_used_pct': '{:.2f}%', 'max_quota_kg': '{:,.0f}', 'total_net_weight_kg': '{:,.0f}'}) # Apply formatting, format quota_used_pct as percentage with 2 decimals
        )
    else:
         st.info("No data to display in the table based on current filters.")


# Section for Graphs
st.header("Visualizations") # Add section title
st.markdown("Visual representations of the filtered data distributions.") # Add descriptive text
with st.container():
     if not filtered_df.empty:
        # Histogram for max_quota_kg with improved labels and tooltips
        chart_max_quota = alt.Chart(filtered_df).mark_bar().encode(
            x=alt.X('max_quota_kg', bin=True, title='Maximum Quota (kg)'), # Add axis title
            y=alt.Y('count()', title='Number of Farmers'), # Add axis title
            tooltip=[alt.Tooltip('max_quota_kg', bin=True, title='Max Quota (kg)'), 'count()'] # Add tooltips
        ).properties(
            title='Distribution of Maximum Quota (kg)' # Add chart title
        ).interactive()
        st.altair_chart(chart_max_quota, use_container_width=True)

        # Histogram for quota_used_pct with improved labels, tooltips, and formatting
        chart_quota_pct = alt.Chart(filtered_df).mark_bar().encode(
            x=alt.X('quota_used_pct', bin=alt.Bin(step=5), title='Quota Used (%)', axis=alt.Axis(format='%')), # Adjust bin step and format axis as percentage
            y=alt.Y('count()', title='Number of Farmers'), # Add axis title
            tooltip=[alt.Tooltip('quota_used_pct', bin=alt.Bin(step=5), title='Quota Used (%)', format='.2f'), 'count()'] # Adjust bin step and format tooltip as percentage
        ).properties(
            title='Distribution of Quota Used (%)' # Add chart title
        ).interactive()
        st.altair_chart(chart_quota_pct, use_container_width=True)

        # Histogram for total_net_weight_kg with improved labels and tooltips
        chart_total_weight = alt.Chart(filtered_df).mark_bar().encode(
            x=alt.X('total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), # Add axis title, use total_net_weight_kg from quota_view
            y=alt.Y('count()', title='Number of Farmers'), # Add axis title
            tooltip=[alt.Tooltip('total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), 'count()'] # Add tooltips, use total_net_weight_kg from quota_view
        ).properties(
            title='Distribution of Total Net Weight (kg)' # Add chart title
        ).interactive()
        st.altair_chart(chart_total_weight, use_container_width=True)
     else:
          st.info("No data to display in visualizations based on current filters.")


# Add a note about deployment and requirements
st.sidebar.markdown("---")
st.sidebar.markdown("This dashboard requires the `streamlit`, `supabase`, `pandas`, and `altair` libraries.")
st.sidebar.markdown("For deployment, ensure these dependencies are listed in a `requirements.txt` file.")
st.sidebar.markdown("Secure your Supabase credentials using Streamlit Secrets (`.streamlit/secrets.toml`).")