
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import altair as alt
import sys

# Re-initialize Supabase client (using placeholder values as before, but prefer secrets)
try:
    # Access secrets using .get() to avoid raising KeyError directly
    SUPABASE_URL = st.secrets.get("supabase", {}).get("url")
    SUPABASE_KEY = st.secrets.get("supabase", {}).get("key")

    # Check if secrets were successfully retrieved
    if not SUPABASE_URL or not SUPABASE_KEY:
         raise KeyError("Supabase secrets not found in Streamlit Secrets.")

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
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    st.sidebar.success("Connected to Supabase.") # Add connection status to sidebar
except Exception as e:
    st.sidebar.error(f"Failed to connect to Supabase: {e}")
    st.stop() # Stop execution if connection fails


# Fetch data (including joining and data preparation)
farmers_table_name = 'farmers'
traceability_table_name = 'traceability'

st.title("Farmer Cocoa Quota Dashboard") # Main dashboard title
st.markdown("Explore and analyze farmer cocoa quota utilization data.") # Add a brief description

try:
    # Add a spinner to indicate data loading
    with st.spinner(f"Fetching data from {farmers_table_name} and {traceability_table_name}..."):
        response_farmers = supabase.from_(farmers_table_name).select('farmer_id, max_quota_kg, quota_status, cooperative_name, certification').execute()
        data_farmers = response_farmers.data

        response_traceability = supabase.from_(traceability_table_name).select('farmer_id, export_lot, exporter, total_net_weight_kg').execute()
        data_traceability = response_traceability.data


    if data_farmers and data_traceability:
        df_farmers = pd.DataFrame(data_farmers)
        df_traceability = pd.DataFrame(data_traceability)

        # 1. Group the df_traceability DataFrame by farmer_id and calculate the sum of total_net_weight_kg
        if not df_traceability.empty:
            df_traceability_agg = df_traceability.groupby('farmer_id')['total_net_weight_kg'].sum().reset_index()
            df_traceability_agg.rename(columns={'total_net_weight_kg': 'aggregated_total_net_weight_kg'}, inplace=True)
        else:
            df_traceability_agg = pd.DataFrame(columns=['farmer_id', 'aggregated_total_net_weight_kg'])
            st.warning("Traceability DataFrame is empty, aggregation skipped.")


        # 2. Ensure the max_quota_kg column in df_farmers is numeric, coercing errors.
        if not df_farmers.empty:
            df_farmers['max_quota_kg'] = pd.to_numeric(df_farmers['max_quota_kg'], errors='coerce')
        else:
            st.warning("Farmers DataFrame is empty, cannot process 'max_quota_kg'.")


        # 3. Join df_farmers and df_traceability_agg DataFrames on the farmer_id column.
        if not df_farmers.empty:
            df_combined = pd.merge(df_farmers, df_traceability_agg, on='farmer_id', how='left')
        else:
            df_combined = pd.DataFrame()
            st.warning("Farmers DataFrame is empty, combined DataFrame is empty.")

        # Continue processing only if df_combined is not empty
        if not df_combined.empty:
            # 4. Fill any missing aggregated_total_net_weight_kg values with 0
            df_combined['aggregated_total_net_weight_kg'].fillna(0, inplace=True)

            # 5. Calculate the quota_used_pct, handling potential division by zero
            # Replace 0 max_quota_kg with NaN before division to avoid ZeroDivisionError, then fill inf with 0
            df_combined['max_quota_kg_clean'] = df_combined['max_quota_kg'].replace(0, pd.NA)
            df_combined['quota_used_pct'] = (df_combined['aggregated_total_net_weight_kg'] / df_combined['max_quota_kg_clean']).fillna(0)
            df_combined.drop('max_quota_kg_clean', axis=1, inplace=True) # Drop the temporary column

            # 6. Ensure specified columns have missing values filled with 'Unknown'
            for col in ['quota_status', 'cooperative_name', 'certification']:
                if col in df_combined.columns:
                    df_combined[col].fillna('Unknown', inplace=True)
                else:
                    st.warning(f"Column '{col}' not found in combined DataFrame.")
                    # Add the column with 'Unknown' if it doesn't exist, to avoid future errors
                    df_combined[col] = 'Unknown'

            # Also fillna for exporter and export_lot from traceability if they exist after join
            for col in ['exporter', 'export_lot']:
                 if col in df_combined.columns:
                     df_combined[col].fillna('Unknown', inplace=True)
                 else:
                      # Add the column with 'Unknown' if it doesn't exist, to avoid future errors
                      df_combined[col] = 'Unknown'


            # 7. Create a new categorical column descriptive_quota_status
            def categorize_quota_status(pct):
                """Categorizes the quota usage percentage into descriptive statuses."""
                if pd.isna(pct):
                    return 'Unknown' # Handle potential NaNs after fillna
                elif pct < 0.5:
                    return 'Underutilized'
                elif pct >= 0.5 and pct < 1.0:
                    return 'Meeting Quota'
                elif pct >= 1.0:
                    return 'Exceeding Quota'
                else:
                    return 'Unknown'

            df_combined['descriptive_quota_status'] = df_combined['quota_used_pct'].apply(categorize_quota_status)


            # Section for Filters
            st.sidebar.header("Filter Data") # Add section title
            st.sidebar.markdown("Adjust the filters below to refine the data displayed in the dashboard.") # Add descriptive text

            with st.sidebar.container():
                # Filter for exporter
                exporter_options = df_combined['exporter'].unique().tolist()
                selected_exporters = st.sidebar.multiselect(
                    "Filter by Exporter",
                    exporter_options,
                    default=exporter_options
                )

                # Filter for quota_status
                quota_status_options = df_combined['quota_status'].unique().tolist()
                selected_quota_statuses = st.sidebar.multiselect(
                    "Filter by Quota Status",
                    quota_status_options,
                    default=quota_status_options
                )

                # Filter for cooperative_name
                cooperative_options = df_combined['cooperative_name'].unique().tolist()
                selected_cooperatives = st.sidebar.multiselect(
                    "Filter by Cooperative Name",
                    cooperative_options,
                    default=cooperative_options
                )

                # Filter for certification
                certification_options = df_combined['certification'].unique().tolist()
                selected_certifications = st.sidebar.multiselect(
                    "Filter by Certification",
                    certification_options,
                    default=certification_options
                )

                # Filter for farmer_id (text input)
                farmer_id_search = st.sidebar.text_input("Search by Farmer ID (substring search)").lower()


                # Filter for quota_used_pct range
                min_quota_pct, max_quota_pct = st.sidebar.slider(
                    "Filter by Quota Used (%)",
                    float(df_combined['quota_used_pct'].min()),
                    float(df_combined['quota_used_pct'].max()),
                    (float(df_combined['quota_used_pct'].min()), float(df_combined['quota_used_pct'].max())),
                    format="%.2f"
                )


            # Apply filters
            filtered_df = df_combined[
                (df_combined['exporter'].isin(selected_exporters)) &
                (df_combined['quota_status'].isin(selected_quota_statuses)) &
                (df_combined['cooperative_name'].isin(selected_cooperatives)) &
                (df_combined['certification'].isin(selected_certifications)) &
                (df_combined['quota_used_pct'] >= min_quota_pct) &
                (df_combined['quota_used_pct'] <= max_quota_pct)
            ].copy() # Use .copy() to avoid SettingWithCopyWarning

            # Apply farmer_id text filter
            if farmer_id_search:
                 filtered_df = filtered_df[filtered_df['farmer_id'].astype(str).str.lower().str.contains(farmer_id_search)].copy()


            # Display a warning if no data matches the filters
            if filtered_df.empty:
                st.warning("No data matches the selected filters.")
                # Continue execution to show empty sections or add st.stop() if desired
                # st.stop() # Uncomment to stop if no data


            # Section for Key Metrics
            st.header("Key Metrics") # Add section title
            st.markdown("Summary statistics for the filtered data.") # Add descriptive text
            with st.container():
                # Calculate key metrics from the filtered data
                total_farmers = filtered_df['farmer_id'].nunique() if not filtered_df.empty else 0
                average_quota_used_pct = filtered_df['quota_used_pct'].mean() if not filtered_df.empty else 0
                total_max_quota_kg = filtered_df['max_quota_kg'].sum() if not filtered_df.empty else 0
                total_net_weight_kg = filtered_df['aggregated_total_net_weight_kg'].sum() if not filtered_df.empty else 0 # Use aggregated weight


                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.subheader("Total Farmers") # Add metric title
                    st.metric(label="Total Farmers", value=total_farmers) # Use st.metric for better formatting and appearance
                with col2:
                    st.subheader("Average Quota Used (%)") # Add metric title
                    st.metric(label="Average Quota Used (%)", value=f"{average_quota_used_pct:.2%}") # Format as percentage
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
                        sorted_df[['farmer_id', 'max_quota_kg', 'aggregated_total_net_weight_kg', 'quota_used_pct', 'quota_status', 'descriptive_quota_status', 'cooperative_name', 'certification', 'exporter', 'export_lot']].style
                        .format({'quota_used_pct': '{:.2%}', 'max_quota_kg': '{:,.0f}', 'aggregated_total_net_weight_kg': '{:,.0f}'}) # Apply formatting
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
                        x=alt.X('quota_used_pct', bin=alt.Bin(step=0.05), title='Quota Used (%)', axis=alt.Axis(format='%')), # Add axis title and format axis as percentage
                        y=alt.Y('count()', title='Number of Farmers'), # Add axis title
                        tooltip=[alt.Tooltip('quota_used_pct', bin=alt.Bin(step=0.05), title='Quota Used (%)', format='.2%'), 'count()'] # Add tooltips and format tooltip as percentage
                    ).properties(
                        title='Distribution of Quota Used (%)' # Add chart title
                    ).interactive()
                    st.altair_chart(chart_quota_pct, use_container_width=True)

                    # Histogram for total_net_weight_kg with improved labels and tooltips
                    chart_total_weight = alt.Chart(filtered_df).mark_bar().encode(
                        x=alt.X('aggregated_total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), # Add axis title, use aggregated weight
                        y=alt.Y('count()', title='Number of Farmers'), # Add axis title
                        tooltip=[alt.Tooltip('aggregated_total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), 'count()'] # Add tooltips, use aggregated weight
                    ).properties(
                        title='Distribution of Total Net Weight (kg)' # Add chart title
                    ).interactive()
                    st.altair_chart(chart_total_weight, use_container_width=True)
                 else:
                      st.info("No data to display in visualizations based on current filters.")


        else:
            st.warning(f"No data found in the '{farmers_table_name}' or '{traceability_table_name}' tables or the join resulted in an empty dataset. Please check the database connection, table names, and data.")

except Exception as e:
    st.error(f"An error occurred: {e}")
    st.error("Please ensure your Supabase credentials are correct and the database is accessible.")

# Add a note about deployment and requirements
st.sidebar.markdown("---")
st.sidebar.markdown("This dashboard requires the `streamlit`, `supabase`, `pandas`, and `altair` libraries.")
st.sidebar.markdown("For deployment, ensure these dependencies are listed in a `requirements.txt` file.")
st.sidebar.markdown("Secure your Supabase credentials using Streamlit Secrets (`.streamlit/secrets.toml`).")