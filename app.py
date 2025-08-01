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
    # Access secrets using .get() and handle potential None return
    supabase_secrets = st.secrets.get("supabase", {})
    if supabase_secrets is not None:
        SUPABASE_URL = supabase_secrets.get("url")
        SUPABASE_KEY = supabase_secrets.get("key")
    else:
         # If st.secrets.get("supabase", {}) returned None, it means the key 'supabase' was not found
         raise KeyError("Supabase secrets section not found in Streamlit Secrets.")


    # Check if secrets were successfully retrieved. If not, a KeyError will be raised.
    if not SUPABASE_URL or not SUPABASE_KEY:
         raise KeyError("Supabase URL or Key not found or incomplete in Streamlit Secrets under [supabase].")

except KeyError as e:
    st.warning(f"Supabase secrets not found in Streamlit Secrets: {e}. Using placeholder values.")
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


# Function to load data in batches
def load_data_batched(table_name, select_columns, page_size=1000):
    """Fetches data from a Supabase table in batches."""
    offset = 0
    all_rows = []
    try:
        while True:
            result = supabase.table(table_name).select(select_columns).range(offset, offset + page_size - 1).execute()
            rows = result.data

            if rows is None:
                st.error(f"Failed to fetch data from '{table_name}' — no data returned.")
                return pd.DataFrame()  # Return empty DataFrame on error

            if not rows:
                break

            all_rows.extend(rows)
            offset += page_size

        return pd.DataFrame(all_rows)
    except Exception as e:
        st.error(f"An error occurred during batched data loading from '{table_name}': {e}")
        return pd.DataFrame()
df_combined = pd.DataFrame()
filtered_df = pd.DataFrame()  # ← TO DODAJ OD RAZU PO df_combined



quota_view_name = 'quota_view'
traceability_table_name = 'traceability'

st.title("Farmer Cocoa Quota Dashboard") # Main dashboard title
st.markdown("Explore and analyze farmer cocoa quota utilization data.") # Add a brief description

df_combined = pd.DataFrame() # Initialize df_combined as empty DataFrame
data_quota = None
data_traceability = None

if supabase: # Only attempt to fetch data if supabase client is initialized
    try:
        # Add a spinner to indicate data loading
        with st.spinner(f"Fetching data from {quota_view_name} and {traceability_table_name}..."):
            # Fetch data from quota_view using batched loading
            # Ensure we select only the columns needed from the view
            df_quota = load_data_batched(quota_view_name, 'farmer_id, max_quota_kg, total_net_weight_kg, quota_used_pct, quota_status')


            # Fetch data from traceability using batched loading
            # Ensure we select only the columns needed for joining and filtering
            df_traceability = load_data_batched(traceability_table_name, 'farmer_id, export_lot, exporter, cooperative_name, certification')


        if not df_quota.empty and not df_traceability.empty:
            # Process traceability data: group by farmer_id and get unique values for filtering columns
            # Ensure farmer_id is string for grouping
            df_traceability['farmer_id'] = df_traceability['farmer_id'].astype(str).str.strip().str.lower()
            df_traceability_processed = df_traceability.groupby('farmer_id').agg({
            'export_lot': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
            'exporter': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
            'cooperative_name': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
            'certification': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0]
        }).reset_index()


            # Join dataframes on 'farmer_id'
            # Ensure farmer_id columns are of the same type for merging
            df_quota['farmer_id'] = df_quota['farmer_id'].astype(str).str.strip().str.lower()
            df_traceability_processed['farmer_id'] = df_traceability_processed['farmer_id'].astype(str).str.strip().str.lower()


            df_combined = pd.merge(df_traceability_processed, df_quota, on='farmer_id', how='left')


        elif not df_quota.empty and df_traceability.empty:
            df_combined = df_quota.copy() # If traceability is empty, just use quota data and add empty columns
            for col in ['export_lot', 'exporter', 'cooperative_name', 'certification']:
                 df_combined[col] = None # Add columns with None values
            st.warning("Traceability DataFrame is empty after fetching, cannot process filtering columns.")
        else:
            df_combined = pd.DataFrame() # Ensure df_combined is empty if quota data is empty
            st.warning(f"No data found in the '{quota_view_name}' or '{traceability_table_name}' after fetching. Check table names and data.")


        # Continue processing only if df_combined is not empty
        if not df_combined.empty:
            # Ensure relevant columns are numeric (these should be from quota_view based on its definition)
            df_combined['max_quota_kg'] = pd.to_numeric(df_combined['max_quota_kg'], errors='coerce')
            df_combined['total_net_weight_kg'] = pd.to_numeric(df_combined['total_net_weight_kg'], errors='coerce')
            df_combined['quota_used_pct'] = pd.to_numeric(df_combined['quota_used_pct'], errors='coerce')


            # Handle missing values - filling with 0 for numeric and 'Unknown' for text/categorical
            df_combined['max_quota_kg'].fillna(0, inplace=True)
            df_combined['total_net_weight_kg'].fillna(0, inplace=True)
            df_combined['quota_used_pct'].fillna(0, inplace=True)

            for col in ['quota_status', 'export_lot', 'exporter', 'cooperative_name', 'certification']:
                # Check if column exists before trying to fillna (important if join resulted in empty trace data)
                if col in df_combined.columns:
                    df_combined[col].fillna('Unknown', inplace=True)
                else:
                    # This case should ideally not happen with how the join is structured
                    st.warning(f"Column '{col}' not found in combined DataFrame during final fillna.")
                    df_combined[col] = 'Unknown' # Add column with 'Unknown' if it got missed


            # --- Add this section to display df_combined before filtering ---
            st.subheader("Combined Data Before Filtering")

            def color_quota_status(val):
                if val == "EXCEEDED":
                    return "color: red"
                elif val == "WARNING":
                    return "color: orange"
                elif val == "OK":
                    return "color: green"
                return ""

            styled_combined = df_combined.style \
                .format({'quota_used_pct': '{:.2f}%', 'max_quota_kg': '{:,.1f}', 'total_net_weight_kg': '{:,.1f}'}) \
                .applymap(color_quota_status, subset=['quota_status'])

            st.dataframe(styled_combined)

            # -------------------------------------------------------------


            # Section for Filters
            st.sidebar.header("Filter Data") # Add section title
            st.sidebar.markdown("Adjust the filters below to refine the data displayed in the dashboard.") # Add descriptive text

            with st.sidebar.container():
                 # Ensure filter options are generated only if df_combined is not empty
                if not df_combined.empty:
                    # Filter for exporter
                    exporter_options = ['All'] + sorted(df_combined['exporter'].unique().tolist())
                    selected_exporters = st.sidebar.multiselect(
                        "Filter by Exporter",
                        exporter_options,
                        default=exporter_options
                    )
                    if 'All' in selected_exporters and len(selected_exporters) > 1:
                         selected_exporters = [opt for opt in selected_exporters if opt != 'All']
                    elif 'All' in selected_exporters and len(selected_exporters) == 1 and 'All' in exporter_options:
                         selected_exporters = sorted([opt for opt in exporter_options if opt != 'All'])
                    elif 'All' in selected_exporters and len(selected_exporters) == 1 and 'All' not in exporter_options:
                         selected_exporters = exporter_options


                    # Filter for quota_status (using the status from the view)
                    quota_status_options = ['All'] + sorted(df_combined['quota_status'].unique().tolist())
                    selected_quota_statuses = st.sidebar.multiselect(
                        "Filter by Quota Status",
                        quota_status_options,
                        default=quota_status_options
                    )
                    if 'All' in selected_quota_statuses and len(selected_quota_statuses) > 1:
                         selected_quota_statuses = [opt for opt in selected_quota_statuses if opt != 'All']
                    elif 'All' in selected_quota_statuses and len(selected_quota_statuses) == 1 and 'All' in quota_status_options:
                         selected_quota_statuses = sorted([opt for opt in quota_status_options if opt != 'All'])
                    elif 'All' in selected_quota_statuses and len(selected_quota_statuses) == 1 and 'All' not in quota_status_options:
                         selected_quota_statuses = quota_status_options


                    # Filter for cooperative_name
                    cooperative_options = ['All'] + sorted(df_combined['cooperative_name'].unique().tolist())
                    selected_cooperatives = st.sidebar.multiselect(
                        "Filter by Cooperative Name",
                        cooperative_options,
                        default=cooperative_options
                    )
                    if 'All' in selected_cooperatives and len(selected_cooperatives) > 1:
                         selected_cooperatives = [opt for opt in selected_cooperatives if opt != 'All']
                    elif 'All' in selected_cooperatives and len(selected_cooperatives) == 1 and 'All' in cooperative_options:
                         selected_cooperatives = sorted([opt for opt in cooperative_options if opt != 'All'])
                    elif 'All' in selected_cooperatives and len(selected_cooperatives) == 1 and 'All' not in cooperative_options:
                        selected_cooperatives = cooperative_options


                    # Filter for certification
                    certification_options = ['All'] + sorted(df_combined['certification'].unique().tolist())
                    selected_certifications = st.sidebar.multiselect(
                        "Filter by Certification",
                        certification_options,
                        default=certification_options
                    )
                    if 'All' in selected_certifications and len(selected_certifications) > 1:
                         selected_certifications = [opt for opt in selected_certifications if opt != 'All']
                    elif 'All' in selected_certifications and len(selected_certifications) == 1 and 'All' in certification_options:
                         selected_certifications = sorted([opt for opt in certification_options if opt != 'All'])
                    elif 'All' in selected_certifications and len(selected_certifications) == 1 and 'All' not in certification_options:
                        selected_certifications = certification_options


                    # Filter for farmer_id (text input)
                    farmer_id_search = st.sidebar.text_input("Search by Farmer ID (substring search)").lower()


                    # Filter for quota_used_pct range
                    min_quota_pct, max_quota_pct = st.sidebar.slider(
                        "Filter by Quota Used (%)",
                        float(df_combined['quota_used_pct'].min()) if 'quota_used_pct' in df_combined.columns and not df_combined.empty else 0.0,
                        float(df_combined['quota_used_pct'].max()) if 'quota_used_pct' in df_combined.columns and not df_combined.empty else 100.0,
                        (float(df_combined['quota_used_pct'].min()) if 'quota_used_pct' in df_combined.columns and not df_combined.empty else 0.0, float(df_combined['quota_used_pct'].max()) if 'quota_used_pct' in df_combined.columns and not df_combined.empty else 100.0),
                        format="%.2f"
                    )
                else:
                    st.sidebar.info("Load data to enable filters.")
                    selected_exporters = []
                    selected_quota_statuses = []
                    selected_cooperatives = []
                    selected_certifications = []
                    farmer_id_search = ""
                    min_quota_pct = 0.0
                    max_quota_pct = 100.0


                # Apply filters
                # Apply filters only if df_combined is not empty
                if not df_combined.empty:
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
                else:
                    filtered_df = pd.DataFrame() # filtered_df is empty if df_combined was empty

    except Exception as e:
        st.error(f"An error occurred during data fetching or processing: {e}")
        st.error("Please ensure your Supabase credentials are correct and the database is accessible.")
        filtered_df = pd.DataFrame() # Ensure filtered_df is empty if an error occurred

else:
    st.error("Supabase client not initialized. Cannot fetch data.")
    filtered_df = pd.DataFrame() # Ensure filtered_df is empty if supabase client is not initialized


# Display a warning if no data matches the filters
if filtered_df.empty and (supabase and (not df_combined.empty)):
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
            ["Ascending", "Descending"],
            index=1
        )

        if sort_order == "Ascending":
            sorted_df = filtered_df.sort_values(by='quota_used_pct', ascending=True)
        else:
            sorted_df = filtered_df.sort_values(by='quota_used_pct', ascending=False)

        def color_quota_status(val):
            color = ""
            if val == "EXCEEDED":
                color = "red"
            elif val == "WARNING":
                color = "orange"
            elif val == "OK":
                color = "green"
            return f"color: {color}"

        styled_df = sorted_df[['farmer_id', 'max_quota_kg', 'total_net_weight_kg', 'quota_used_pct', 'quota_status', 'cooperative_name', 'certification', 'exporter', 'export_lot']].style \
            .format({'quota_used_pct': '{:.2f}%', 'max_quota_kg': '{:,.0f}', 'total_net_weight_kg': '{:,.0f}'}) \
            .applymap(color_quota_status, subset=['quota_status'])

        st.dataframe(styled_df)

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

                # Pie chart for Quota Status distribution
        quota_status_counts = filtered_df['quota_status'].value_counts().reset_index()
        quota_status_counts.columns = ['quota_status', 'count']

        pie_chart = alt.Chart(quota_status_counts).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field="count", type="quantitative"),
            color=alt.Color(field="quota_status", type="nominal",
                            scale=alt.Scale(domain=["OK", "WARNING", "EXCEEDED"],
                                            range=["green", "orange", "red"])),
            tooltip=["quota_status", "count"]
        ).properties(
            title="Quota Status Distribution"
        )

        st.altair_chart(pie_chart, use_container_width=True)

     else:
          st.info("No data to display in visualizations based on current filters.")


# Add a note about deployment and requirements
st.sidebar.markdown("---")
st.sidebar.markdown("This dashboard requires the `streamlit`, `supabase`, `pandas`, and `altair` libraries.")
st.sidebar.markdown("For deployment, ensure these dependencies are listed in a `requirements.txt` file.")
st.sidebar.markdown("Secure your Supabase credentials using Streamlit Secrets (`.streamlit/secrets.toml`).")