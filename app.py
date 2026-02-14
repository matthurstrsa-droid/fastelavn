import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import numpy as np

# --- 1. BOOTSTRAP & ERROR HANDLING ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide")

# This prevents the white screen if secrets are missing
if "connections" not in st.secrets or "my_bakery_db" not in st.secrets["connections"]:
    st.error("Missing Database Secrets! Please check your Streamlit Cloud secrets.")
    st.stop()

# --- 2. SESSION STATE (The Engine) ---
# We use .get() to avoid key errors that cause white screens
if "arrival_times" not in st.session_state: st.session_state.arrival_times = {}
if "watchlist" not in st.session_state: st.session_state.watchlist = []
if "selected_bakery" not in st.session_state: st.session_state.selected_bakery = None
if "user_nickname" not in st.session_state: st.session_state.user_nickname = "Hobbyist"

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

# --- 3. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    # Replace with your actual Sheet ID
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=5) # Increased TTL slightly to prevent spamming the white screen
def load_data():
    try:
        data = get_worksheet().get_all_records()
        df = pd.DataFrame(data)
        df.columns = [c.strip() for c in df.columns]
        # Robust numeric conversion
        for col in ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 4. THE ACTION CENTER (UI Logic) ---
st.title("🥯 BolleQuest")

# Search Bar - Logic fixed for deep search
search_query = st.text_input("🔍 Search (vegan, flavors, bakery...)", "").lower().strip()

# Filters
filtered = df_raw.copy()
if search_query:
    # This combines the text from 3 columns into one search string to avoid missing "vegan"
    corpus = (filtered['Bakery Name'].astype(str) + " " + 
              filtered['Fastelavnsbolle Type'].astype(str) + " " + 
              filtered['Comment'].astype(str)).str.lower()
    filtered = filtered[corpus.str.contains(search_query, na=False)]

# --- 5. TABS ---
t_map, t_stream, t_app = st.tabs(["📍 Map", "🧵 Stream", "⚙️ Settings"])

with t_map:
    # If a bakery is selected, show the Arrival/Review Popover
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_data = df_raw[df_raw['Bakery Name'] == name].iloc[0]
        
        with st.expander(f"Selected: {name}", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Stock:** {int(b_data['Stock'])} buns left")
                st.write(f"**Current Flavor:** {b_data['Fastelavnsbolle Type']}")
            
            with col2:
                # Arrival Logic
                if name not in st.session_state.arrival_times:
                    if st.button("🏁 I just arrived at the line"):
                        st.session_state.arrival_times[name] = get_now_dk()
                        st.rerun()
                else:
                    wait_so_far = (get_now_dk() - st.session_state.arrival_times[name]).seconds // 60
                    st.info(f"⏱️ You've been in line for {wait_so_far} mins")

            # Review Form
            if int(b_data['Stock']) > 0:
                with st.form("review_form"):
                    t_f = st.text_input("Confirm Flavor", value=b_data['Fastelavnsbolle Type'])
                    t_r = st.slider("Rating", 1.0, 5.0, 4.0, 0.5)
                    t_c = st.text_area("Comment")
                    if st.form_submit_button("Post Review"):
                        # Calculate final wait time if they logged arrival
                        final_wait = 0
                        if name in st.session_state.arrival_times:
                            final_wait = (get_now_dk() - st.session_state.arrival_times[name]).seconds // 60
                            del st.session_state.arrival_times[name]
                        
                        # APPEND TO GOOGLE SHEET
                        # [Bakery, Flavor, Photo, Addr, Lat, Lon, Date, Cat, User, Rating, Price, Stock, Time, Key, Comment, WaitTime]
                        get_worksheet().append_row([
                            name, t_f, "", b_data['Address'], b_data['lat'], b_data['lon'],
                            get_now_dk().strftime("%Y-%m-%d"), "User", st.session_state.user_nickname,
                            t_r, b_data['Price'], b_data['Stock'], get_now_dk().strftime("%H:%M"),
                            "", t_c, final_wait
                        ], value_input_option='USER_ENTERED')
                        
                        st.session_state.selected_bakery = None
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.error("🚫 Sold out. Reviews disabled.")
                if st.button("Close"): 
                    st.session_state.selected_bakery = None
                    st.rerun()

    # The actual Map
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] == 0 else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name']).add_to(m)
    
    map_data = st_folium(m, width=700, height=450)
    if map_data["last_object_clicked_tooltip"]:
        if st.session_state.selected_bakery != map_data["last_object_clicked_tooltip"]:
            st.session_state.selected_bakery = map_data["last_object_clicked_tooltip"]
            st.rerun()
