import streamlit as st
import pandas as pd
from databricks import sql
import os
import uuid
from datetime import date

# 1. Configuration
# In Databricks Apps, serverless compute environment variables are injected automatically.
TARGET_TABLE = "default.customer_packages"  # Update this with your catalog.schema.table if necessary
RAW_CSV_PATH = "/Volumes/data_dev/default/bits_project/generated_data.csv"

st.set_page_config(page_title="Customer Package Management", layout="centered")
st.title("🌐 Customer Package Onboarding Form")
st.markdown("---")

# --- Load Raw Data from UC Volume ---
@st.cache_data(ttl=300) 
def load_volume_data(path):
    try:
        if os.path.exists(path):
            return pd.read_csv(path)
        else:
            st.error(f"Volume path not found: {path}. Ensure the volume path is correct and accessible.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading CSV from Volume: {str(e)}")
        return pd.DataFrame()

raw_df = load_volume_data(RAW_CSV_PATH)

# --- Dynamic Lookups from CSV ---
def fetch_customer_metrics(df, name):
    if df.empty or not name:
        return 0, "[]"
    match = df[df['customer_name'].str.lower() == name.lower()]
    if not match.empty:
        latest_row = match.iloc[-1]
        prev_count = int(latest_row.get('previous_packages_count', 0))
        history = str(latest_row.get('package_change_history', '[]'))
        return prev_count, history
    return 0, "[]"

# Populate dropdown options from CSV columns dynamically
if not raw_df.empty and 'current_package_name' in raw_df.columns:
    package_options = sorted(raw_df['current_package_name'].dropna().unique().tolist())
    speed_options_down = sorted([int(x) for x in raw_df['current_speed_mbps_down'].dropna().unique()])
    speed_options_up = sorted([int(x) for x in raw_df['current_speed_mbps_up'].dropna().unique()])
else:
    # Safe fallbacks if CSV is loading or columns differ
    package_options = ["Basic Fiber", "Standard Broadband", "Premium Ultra", "GigaMax Pro"]
    speed_options_down = [50, 100, 200, 300, 500, 1000]
    speed_options_up = [10, 50, 100, 200, 300, 500, 1000]

# 2. Form UI
with st.form("customer_onboarding_form", clear_on_submit=True):
    st.subheader("📋 Customer Details")
    customer_name = st.text_input("Customer Name *", placeholder="John Doe")
    customer_address = st.text_area("Customer Address *", placeholder="123 Main St, City, Country")
    
    st.markdown("---")
    st.subheader("⚡ Package Configuration")
    current_package_name = st.selectbox("Current Package Name", options=package_options)
    current_speed_mbps_down = st.selectbox("Current Download Speed (Mbps)", options=speed_options_down)
    current_speed_mbps_up = st.selectbox("Current Upload Speed (Mbps)", options=speed_options_up)

    # Automatically computed fields
    autogen_customer_id = f"CUST-{uuid.uuid4().hex[:8].upper()}"
    current_service_date = date.today()
    prev_packages, change_history = fetch_customer_metrics(raw_df, customer_name)
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1: 
        st.info(f"**Generated ID:** `{autogen_customer_id}`")
    with col2: 
        st.info(f"**Start Date:** `{current_service_date}`")

    submitted = st.form_submit_button("Submit & Save Record")

# 3. Write-Back execution
if submitted:
    if not customer_name or not customer_address:
        st.error("❌ Customer Name and Customer Address are required fields.")
    else:
        try:
            # Connect dynamically using auto-injected cluster variables
            with sql.connect(
                server_hostname=os.environ.get("DATABRICKS_HOST"),
                http_path=os.environ.get("DATABRICKS_WAREHOUSE_HTTP_PATH"), 
                credentials_provider=lambda: os.environ.get("DATABRICKS_OAUTH_TOKEN")
            ) as conn:
                
                with conn.cursor() as cursor:
                    insert_query = f"""
                        INSERT INTO {TARGET_TABLE} (
                            customer_id, customer_name, customer_address, 
                            current_package_name, current_speed_mbps_down, current_speed_mbps_up, 
                            service_start_date, previous_packages_count, package_change_history
                        )
                        VALUES (
                            %(cust_id)s, %(name)s, %(addr)s, %(pkg_name)s, 
                            %(speed_down)s, %(speed_up)s, CURRENT_DATE(), 
                            %(prev_cnt)s, %(history)s
                        )
                    """
                    cursor.execute(insert_query, {
                        "cust_id": autogen_customer_id,
                        "name": customer_name,
                        "addr": customer_address,
                        "pkg_name": current_package_name,
                        "speed_down": int(current_speed_mbps_down),
                        "speed_up": int(current_speed_mbps_up),
                        "prev_cnt": int(prev_packages),
                        "history": change_history
                    })
            st.success(f"🎉 Success! Record saved for {customer_name}.")
            st.balloons()
        except Exception as e:
            st.error(f"❌ Execution Error: {str(e)}")
