import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import numpy as np
import cloudinary.uploader

# --- 1. CONFIG & SAFETY ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

# Initialize Session States
states = {
    "selected_bakery": None,
    "merchant_bakery": None,
    "user_nickname": "BunHunter",
    "arrival_times": {}, 
    "watchlist": [],
    "user_filter": None
}
for key, val in states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 2. DATA ENGINE ---
@st.cache_resource
def get_gs_client():
    creds = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    try:
        df = pd.DataFrame(get_worksheet().get_all_records())
        if df.empty: return df
        df.columns = [c.strip() for c in df.columns]
        
        # Defensive: Ensure these columns exist even if not in Sheet yet
        expected = ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time', 'Photo URL', 'Comment']
        for col in expected:
            if col not in df.columns:
                df[col] = 0.0 if col != 'Comment' and col != 'Photo URL' else ""
            elif col in ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Database Sync Error: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 3. GLOBAL UI ---
st.title("🥯 BolleQuest")

# Search & Filters
search_query = st.text_input("🔍 Search everything...", "").lower().strip()
filtered = df_raw.copy()

if search_query and not filtered.empty:
    corpus = (filtered['Bakery Name'].astype(str) + " " + 
              filtered['Fastelavnsbolle Type'].astype(str) + " " + 
              filtered['Comment'].astype(str)).str.lower()
    filtered = filtered[corpus.str.contains(search_query, na=False)]

# --- 4. TABS ---
t_map, t_stream, t_top, t_settings, t_help = st.tabs(["📍 Map", "🧵 Stream", "🏆 Leaderboard", "⚙️ Settings", "❓ Help"])

with t_map:
    # --- QUEUE & REVIEW INTERFACE ---
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_data = df_raw[df_raw['Bakery Name'] == name].iloc[0]
        is_m = st.session_state.merchant_bakery == name
        
        with st.expander(f"📍 {name} {'(ADMIN)' if is_m else ''}", expanded=True):
            if is_m:
                st.subheader("🧑‍🍳 Official Management")
                ns = st.number_input("Update Stock", 0, 500, int(b_data['Stock']))
                t_f = st.text_input("Official Flavor", b_data['Fastelavnsbolle Type'])
                img = st.file_uploader("New Photo", type=['jpg','png'])
                if st.button("Broadcast Update"):
                    i_url = cloudinary.uploader.upload(img)['secure_url'] if img else b_data['Photo URL']
                    get_worksheet().append_row([name, t_f, i_url, b_data['Address'], b_data['lat'], b_data['lon'], 
                                              get_now_dk().strftime("%Y-%m-%d"), "Merchant", name, 5.0, 
                                              b_data['Price'], ns, get_now_dk().strftime("%H:%M"), "", "Fresh Batch Out!", 0], value_input_option='USER_ENTERED')
                    st.session_state.selected_bakery = None; st.cache_data.clear(); st.rerun()
            
            elif b_data['Stock'] <= 0:
                st.error("🚫 SOLD OUT")
                if st.button("Close"): st.session_state.selected_bakery = None; st.rerun()
            
            else:
                # Step 1: Arrive
                if name not in st.session_state.arrival_times:
                    if st.button("🏁 I've arrived/joined the line"):
                        st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}
                        st.rerun()
                # Step 2: Got Bun
                elif st.session_state.arrival_times[name]["wait"] is None:
                    wait_now = (get_now_dk() - st.session_state.arrival_times[name]["start"]).seconds // 60
                    st.info(f"⏱️ Waiting: {wait_now} mins...")
                    if st.button("🛍️ Got my Bolle!"):
                        st.session_state.arrival_times[name]["wait"] = max(1, wait_now); st.rerun()
                # Step 3: Review
                else:
                    with st.form("rev"):
                        st.success(f"Wait time: {st.session_state.arrival_times[name]['wait']} mins")
                        r_score = st.slider("Rating", 1.0, 5.0, 4.0)
                        r_comm = st.text_area("Comment")
                        if st.form_submit_button("Post Review"):
                            get_worksheet().append_row([name, b_data['Fastelavnsbolle Type'], "", b_data['Address'], b_data['lat'], b_data['lon'],
                                                      get_now_dk().strftime("%Y-%m-%d"), "User", st.session_state.user_nickname,
                                                      r_score, b_data['Price'], b_data['Stock'], get_now_dk().strftime("%H:%M"),
                                                      "", r_comm, st.session_state.arrival_times[name]['wait']], value_input_option='USER_ENTERED')
                            del st.session_state.arrival_times[name]; st.session_state.selected_bakery = None; st.cache_data.clear(); st.rerun()

    # The Map
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] == 0 else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name']).add_to(m)
    st_map = st_folium(m, width="100%", height=500)
    if st_map.get("last_object_clicked_tooltip"):
        if st.session_state.selected_bakery != st_map["last_object_clicked_tooltip"]:
            st.session_state.selected_bakery = st_map["last_object_clicked_tooltip"]; st.rerun()

with t_stream:
    if not filtered.empty:
        stream_df = filtered.sort_values(by=["Date"], ascending=False)
        for i, r in stream_df.iterrows():
            with st.container(border=True):
                st.markdown(f"**{r['Bakery Name']}** | @{r['User']}")
                if r['Photo URL']: st.image(r['Photo URL'], width=300)
                st.write(f"⭐ {r['Rating']} | ⏳ {int(r.get('Wait Time', 0))} min wait")
                if r['Comment']: st.info(r['Comment'])

with t_top:
    st.subheader("🏆 Leaders")
    if not df_raw.empty:
        valid = df_raw[df_raw['Rating'] > 0]
        st.dataframe(valid.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].mean().sort_values(ascending=False), use_container_width=True)

with t_settings:
    st.subheader("👤 User Settings")
    st.session_state.user_nickname = st.text_input("Update Nickname", st.session_state.user_nickname)
    
    st.divider()
    st.subheader("🧑‍🍳 Bakery Dashboard")
    if st.session_state.merchant_bakery:
        st.success(f"Access Active: {st.session_state.merchant_bakery}")
        if st.button("Log Out of Merchant Mode"):
            st.session_state.merchant_bakery = None; st.rerun()
    else:
        key = st.text_input("Enter Bakery Secret Key", type="password")
        if st.button("Unlock Merchant Portal"):
            match = df_raw[df_raw['Bakery Key'].astype(str) == key]
            if not match.empty:
                st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                st.rerun()
            else:
                st.error("Invalid Key")

    st.divider()
    st.subheader("📊 Data Health Check")
    if not df_raw.empty:
        cols = list(df_raw.columns)
        if "Wait Time" in cols:
            st.success("Column 'Wait Time' detected.")
        else:
            st.warning("Column 'Wait Time' missing in Google Sheets. Please add it to avoid errors.")

with t_help:
    st.write("### ❓ FAQ")
    st.markdown("""
    **How do I use the timer?** 1. Click a bakery on the map.  
    2. Click **'I've arrived'** when you get in line.  
    3. Click **'Got my Bolle'** when you receive it.  
    4. The app calculates your wait time automatically for your review!
    """)
