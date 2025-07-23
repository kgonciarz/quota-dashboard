import streamlit as st
import pandas as pd
from supabase import create_client, Client
import altair as alt
import sys

# Check if altair is installed, and install it if not (for deployment preparation)
try:
    import altair as alt
except ImportError:
    st.error("Altair library not found. Attempting to install...")
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "altair"])
        st.success("Altair installed successfully. Please rerun the app.")
        st.stop() # Stop execution after installation
    except Exception as e:
        st.error(f"Failed to install Altair: {e}")
        st.stop()

# Review and refine the existing Streamlit script

# Use Streamlit Secrets for Supabase credentials in a production environment
# Ensure you have created a .streamlit/secrets.toml file with your credentials
# For local testing, you might keep the placeholders or use environment variables
try:
    # Access secrets using .get() to avoid raising KeyError directly
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]



except Exception as e:
    st.error(f"An error occurred while accessing secrets: {e}")
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


# Re-fetch and process data
table_name = 'quota_view'

st.title("Farmer Quota Dashboard") # Main dashboard title
st.markdown("Explore and analyze farmer quota utilization data.") # Add a brief description

try:
    # Add a spinner to indicate data loading
    with st.spinner(f"Fetching data from {table_name}..."):
        response = supabase.from_(table_name).select('farmer_id, max_quota_kg, quota_used_pct, quota_status, total_net_weight_kg').execute()
        data = response.data

    if data:
        df_quota = pd.DataFrame(data)

        # Add data cleaning/processing comments for clarity
        # Ensure 'quota_used_pct', 'max_quota_kg', and 'total_net_weight_kg' are numeric
        df_quota['quota_used_pct'] = pd.to_numeric(df_quota['quota_used_pct'], errors='coerce')
        df_quota['max_quota_kg'] = pd.to_numeric(df_quota['max_quota_kg'], errors='coerce')
        df_quota['total_net_weight_kg'] = pd.to_numeric(df_quota['total_net_weight_kg'], errors='coerce')

        # Handle missing values - filling with 0 for numeric and 'Unknown' for 'quota_status'
        df_quota['quota_used_pct'].fillna(0, inplace=True)
        df_quota['max_quota_kg'].fillna(0, inplace=True)
        df_quota['total_net_weight_kg'].fillna(0, inplace=True)
        df_quota['quota_status'].fillna('Unknown', inplace=True)

        # Create a new categorical quota status column with comments
        def categorize_quota_status(pct):
            """Categorizes the quota usage percentage into descriptive statuses."""
            if pct < 0.5:
                return 'Underutilized'
            elif pct >= 0.5 and pct < 1.0:
                return 'Meeting Quota'
            elif pct >= 1.0:
                return 'Exceeding Quota'
            else:
                return 'Unknown' # Handle potential non-numeric values after coercion and fillna

        df_quota['descriptive_quota_status'] = df_quota['quota_used_pct'].apply(categorize_quota_status)

        # Section for Filters - Add descriptive text and organize using sidebar
        st.sidebar.header("Filter Data")
        st.sidebar.markdown("Adjust the filters below to refine the data displayed in the dashboard.")

        with st.sidebar.container():
            # Filter for quota_status
            quota_status_options = df_quota['quota_status'].unique().tolist()
            selected_quota_statuses = st.sidebar.multiselect(
                "Filter by Quota Status", # Add filter label
                quota_status_options,
                default=quota_status_options
            )

            # Filter for descriptive_quota_status
            descriptive_status_options = df_quota['descriptive_quota_status'].unique().tolist()
            selected_descriptive_statuses = st.sidebar.multiselect(
                "Filter by Descriptive Quota Status", # Add filter label
                descriptive_status_options,
                default=descriptive_status_options
            )

            # Filter for quota_used_pct range - Add label and format slider values
            min_quota_pct, max_quota_pct = st.sidebar.slider(
                "Filter by Quota Used (%)", # Add filter label
                float(df_quota['quota_used_pct'].min()),
                float(df_quota['quota_used_pct'].max()),
                (float(df_quota['quota_used_pct'].min()), float(df_quota['quota_used_pct'].max())),
                format="%.2f" # Format slider values
            )

        # Apply filters
        filtered_df = df_quota[
            (df_quota['quota_status'].isin(selected_quota_statuses)) &
            (df_quota['descriptive_quota_status'].isin(selected_descriptive_statuses)) &
            (df_quota['quota_used_pct'] >= min_quota_pct) &
            (df_quota['quota_used_pct'] <= max_quota_pct)
        ].copy() # Use .copy() to avoid SettingWithCopyWarning

        # Display a warning if no data matches the filters
        if filtered_df.empty:
            st.warning("No data matches the selected filters.")
            st.stop() # Stop execution if no data is available

        # Section for Key Metrics
        st.header("Key Metrics") # Add section title
        st.markdown("Summary statistics for the filtered data.") # Add descriptive text
        with st.container():
            # Calculate key metrics from the filtered data
            total_farmers = filtered_df['farmer_id'].nunique() if not filtered_df.empty else 0
            average_quota_used_pct = filtered_df['quota_used_pct'].mean() if not filtered_df.empty else 0
            total_max_quota_kg = filtered_df['max_quota_kg'].sum() if not filtered_df.empty else 0
            total_net_weight_kg = filtered_df['total_net_weight_kg'].sum() if not filtered_df.empty else 0

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
        st.header("Raw Data Table") # Add section title
        st.markdown("Detailed farmer quota information.") # Add descriptive text
        with st.container():
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
                sorted_df[['farmer_id', 'max_quota_kg', 'quota_used_pct', 'quota_status', 'total_net_weight_kg']].style
                .format({'quota_used_pct': '{:.2%}', 'max_quota_kg': '{:,.0f}', 'total_net_weight_kg': '{:,.0f}'}) # Apply formatting
            )


        # Section for Graphs
        st.header("Visualizations") # Add section title
        st.markdown("Visual representations of the filtered data distributions.") # Add descriptive text
        with st.container():
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
                x=alt.X('total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), # Add axis title
                y=alt.Y('count()', title='Number of Farmers'), # Add axis title
                tooltip=[alt.Tooltip('total_net_weight_kg', bin=True, title='Total Net Weight (kg)'), 'count()'] # Add tooltips
            ).properties(
                title='Distribution of Total Net Weight (kg)' # Add chart title
            ).interactive()
            st.altair_chart(chart_total_weight, use_container_width=True)


    else:
        st.warning(f"No data found in the '{table_name}' table. Please check the database connection and table name.")

except Exception as e:
    st.error(f"An error occurred: {e}")
    st.error("Please ensure your Supabase credentials are correct and the database is accessible.")

# Add a note about deployment and requirements
st.sidebar.markdown("---")
st.sidebar.markdown("This dashboard requires the `streamlit`, `supabase`, `pandas`, and `altair` libraries.")
st.sidebar.markdown("For deployment, ensure these dependencies are listed in a `requirements.txt` file.")
st.sidebar.markdown("Secure your Supabase credentials using Streamlit Secrets (`.streamlit/secrets.toml`).")
