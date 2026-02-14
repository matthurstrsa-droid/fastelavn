import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import pytz
import numpy as np

# --- 1. SESSION STATE & CONFIG ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide")

# Persistent arrival tracking
if "arrival_times" not in st.session_state: st.session_state.arrival_times = {} 
if "watchlist" not in st.session_state: st.session_state.watchlist = []
if "selected_bakery" not in st.session_state: st.session_state.selected_bakery = None

def get_now():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

# --- 2. DATA ENGINE ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    df = pd.DataFrame(get_worksheet().get_all_records())
    # Ensure Wait Time and Arrival columns exist in your sheet or handle them as numeric
    for col in ['lat', 'lon', 'Stock', 'Wait Time']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df_raw = load_data()

# --- 3. CROWD & WAIT LOGIC ---
# Calculate "Crowd" based on check-ins in the last 30 mins
def get_crowd_stats(bakery_name, df):
    now = get_now()
    # Assuming "Last Updated" is in HH:MM format, we convert for comparison
    # For a true stress test, you'd use a full ISO timestamp in the sheet
    recent_reports = df[df['Bakery Name'] == bakery_name].copy()
    # Simple count of reports today as a proxy for crowd
    return len(recent_reports)

# --- 4. ACTION CENTER ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_row = df_raw[df_raw['Bakery Name'] == name].iloc[0]
    is_sold_out = int(b_row['Stock']) <= 0
    
    with st.popover(f"📍 {name}", use_container_width=True):
        crowd_count = get_crowd_stats(name, df_raw)
        st.write(f"👥 **Live Crowd:** {crowd_count} people recently spotted here")
        
        avg_wait = b_row.get('Wait Time', 0)
        st.write(f"⏳ **Avg. Wait Time:** {int(avg_wait)} mins")

        if is_sold_out:
            st.error("🚫 SOLD OUT")
            if name not in st.session_state.watchlist:
                if st.button("🔔 Notify me on restock"):
                    st.session_state.watchlist.append(name); st.rerun()
        else:
            # ARRIVAL TRACKER
            if name not in st.session_state.arrival_times:
                if st.button("🏁 I just arrived / Joined the line", use_container_width=True):
                    st.session_state.arrival_times[name] = get_now()
                    st.toast("Timer started! Post your review when you get your bun.")
                    st.rerun()
            else:
                arrival = st.session_state.arrival_times[name]
                current_wait = (get_now() - arrival).seconds // 60
                st.info(f"⏱️ You've been in line for {current_wait} minutes.")
                
                # REVIEW FORM
                with st.form("review_form"):
                    t_f = st.text_input("Flavor")
                    t_r = st.slider("Rating", 1.0, 5.0, 4.0)
                    t_c = st.text_area("Comment")
                    submit = st.form_submit_button("Post Review & Log Wait Time")
                    
                    if submit:
                        final_wait = (get_now() - arrival).seconds // 60
                        # Update logic: append_row to sheet
                        # Sheet Structure: [Bakery, Flavor, Photo, Addr, Lat, Lon, Date, Cat, User, Rating, Price, Stock, Time, Key, Comment, WaitTime]
                        get_worksheet().append_row([
                            name, t_f, "", b_row['Address'], b_row['lat'], b_row['lon'],
                            datetime.now().strftime("%Y-%m-%d"), "User", st.session_state.user_nickname,
                            t_r, b_row['Price'], b_row['Stock'], get_now().strftime("%H:%M"),
                            "", t_c, final_wait
                        ], value_input_option='USER_ENTERED')
                        
                        del st.session_state.arrival_times[name]
                        st.cache_data.clear(); st.session_state.selected_bakery = None
                        st.balloons(); st.rerun()

# --- 5. TABS ---
# (Map and Stream logic remains the same, but now shows Wait Time in the UI)
