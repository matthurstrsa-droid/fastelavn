import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import numpy as np

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

# Initialize Session States with safe defaults
if "arrival_times" not in st.session_state: st.session_state.arrival_times = {}
if "selected_bakery" not in st.session_state: st.session_state.selected_bakery = None
if "merchant_bakery" not in st.session_state: st.session_state.merchant_bakery = None
if "user_nickname" not in st.session_state: st.session_state.user_nickname = "BunHunter"

# --- 2. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    try:
        data = get_worksheet().get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return df
        df.columns = [c.strip() for c in df.columns]
        
        # Ensure all columns exist and are typed correctly for the UI
        cols = {
            'lat': 0.0, 'lon': 0.0, 'Stock': 0, 'Price': 0, 
            'Rating': 0.0, 'Wait Time': 0, 'Photo URL': "", 'Comment': ""
        }
        for col, val in cols.items():
            if col not in df.columns:
                df[col] = val
            elif col in ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Load Error: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 3. THE LOGIC ENGINE (Sanitized for JSON) ---
def post_to_sheets(row_list):
    """Converts all items to standard Python types to prevent JSON errors."""
    sanitized = []
    for item in row_list:
        if isinstance(item, (np.int64, np.int32)): sanitized.append(int(item))
        elif isinstance(item, (np.float64, np.float32)): sanitized.append(float(item))
        elif pd.isna(item): sanitized.append("")
        else: sanitized.append(item)
    
    get_worksheet().append_row(sanitized, value_input_option='USER_ENTERED')

# --- 4. TABS ---
t_map, t_stream, t_top, t_settings, t_help = st.tabs(["📍 Map", "🧵 Stream", "🏆 Leaderboard", "⚙️ Settings", "❓ Help"])

with t_map:
    # Action Center for Selected Bakery
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_data = df_raw[df_raw['Bakery Name'] == name].iloc[0]
        
        with st.expander(f"Reviewing: {name}", expanded=True):
            # Step 1: Join Line
            if name not in st.session_state.arrival_times:
                if st.button("🏁 I've arrived/Joined the line", use_container_width=True):
                    st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}
                    st.rerun()
            
            # Step 2: Pay/Receive
            elif st.session_state.arrival_times[name]["wait"] is None:
                start = st.session_state.arrival_times[name]["start"]
                current_wait = (get_now_dk() - start).seconds // 60
                st.info(f"⏱️ You've been in line for {current_wait} mins...")
                if st.button("🛍️ Got my Bolle!", type="primary", use_container_width=True):
                    st.session_state.arrival_times[name]["wait"] = max(1, current_wait)
                    st.rerun()
            
            # Step 3: Review
            else:
                final_wait = st.session_state.arrival_times[name]["wait"]
                with st.form("review_form_final"):
                    st.success(f"Wait time recorded: {final_wait} minutes.")
                    t_f = st.text_input("Confirm Flavor", value=str(b_data['Fastelavnsbolle Type']))
                    t_r = st.slider("Rating (1-5)", 1.0, 5.0, 4.0, 0.5)
                    t_c = st.text_area("Your Review")
                    
                    if st.form_submit_button("Submit Review"):
                        # TYPE SANITIZATION BEFORE SENDING
                        row = [
                            str(name), str(t_f), "", str(b_data['Address']), 
                            float(b_data['lat']), float(b_data['lon']),
                            get_now_dk().strftime("%Y-%m-%d"), "User", 
                            str(st.session_state.user_nickname), float(t_r), 
                            float(b_data['Price']), int(b_data['Stock']), 
                            get_now_dk().strftime("%H:%M"), "", str(t_c), int(final_wait)
                        ]
                        post_to_sheets(row)
                        
                        # Reset State
                        del st.session_state.arrival_times[name]
                        st.session_state.selected_bakery = None
                        st.cache_data.clear()
                        st.balloons()
                        st.rerun()
            
            if st.button("Cancel"): 
                st.session_state.selected_bakery = None
                st.rerun()

    # Map Rendering
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in df_raw.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] <= 0 else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name']).add_to(m)
    
    map_res = st_folium(m, width="100%", height=500, key="main_map")
    if map_res.get("last_object_clicked_tooltip"):
        clicked = map_res["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t_stream:
    if not df_raw.empty:
        # Show only user reports in the stream
        stream = df_raw[df_raw['Category'] == 'User'].sort_values(by="Date", ascending=False)
        for _, r in stream.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Bakery Name']}** | @{r['User']}")
                st.write(f"⭐ {r['Rating']} | ⏳ {int(r['Wait Time'])} min wait")
                if r['Comment']: st.info(r['Comment'])

with t_top:
    st.subheader("🏆 The 2026 Rankings")
    if not df_raw.empty:
        rank = df_raw[df_raw['Rating'] > 0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False)
        st.table(rank)

with t_settings:
    st.subheader("⚙️ Settings")
    st.session_state.user_nickname = st.text_input("Change Nickname", st.session_state.user_nickname)
    
    st.divider()
    st.subheader("🧑‍🍳 Merchant Portal")
    if st.session_state.merchant_bakery:
        st.info(f"Logged in as: {st.session_state.merchant_bakery}")
        if st.button("Log Out"): 
            st.session_state.merchant_bakery = None; st.rerun()
    else:
        key_input = st.text_input("Enter Bakery Key", type="password")
        if st.button("Login"):
            match = df_raw[df_raw['Bakery Key'].astype(str) == key_input]
            if not match.empty:
                st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                st.rerun()

with t_help:
    st.markdown("""
    ### 🥨 How to use BolleQuest
    1. **Find a bakery** on the map.
    2. **Join the line** by clicking the 'Arrived' button.
    3. **Eat your bun** and click 'Got my Bolle'.
    4. **Submit your score!** The wait time is calculated automatically.
    """)
