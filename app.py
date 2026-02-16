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
    "arrival_times": {}, # Stores {bakery_name: {"start": time, "wait": mins}}
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
        df.columns = [c.strip() for c in df.columns]
        for col in ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Database Sync Error: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 3. SIDEBAR & GLOBAL SEARCH ---
with st.sidebar:
    st.header("👤 Profile")
    st.session_state.user_nickname = st.text_input("Your Nickname", st.session_state.user_nickname)
    
    if st.session_state.merchant_bakery:
        st.success(f"🧑‍🍳 Merchant: {st.session_state.merchant_bakery}")
        if st.button("Logout Admin"):
            st.session_state.merchant_bakery = None; st.rerun()

    st.divider()
    if st.button("🔄 Clear Filters & Reset"):
        st.session_state.user_filter = None
        st.rerun()

st.title("🥯 BolleQuest")

# Deep Search Logic
search_query = st.text_input("🔍 Search everything (vegan, mocha, bakery name...)", "").lower().strip()
filtered = df_raw.copy()

if search_query:
    corpus = (filtered['Bakery Name'].astype(str) + " " + 
              filtered['Fastelavnsbolle Type'].astype(str) + " " + 
              filtered['Comment'].astype(str)).str.lower()
    filtered = filtered[corpus.str.contains(search_query, na=False)]

if st.session_state.user_filter:
    filtered = filtered[filtered['User'] == st.session_state.user_filter]
    st.info(f"Showing posts by @{st.session_state.user_filter}")
    if st.button("Clear User Filter"): st.session_state.user_filter = None; st.rerun()

# --- 4. TABS ---
t_map, t_stream, t_top, t_help = st.tabs(["📍 Map", "🧵 Stream", "🏆 Leaderboard", "❓ Help/FAQ"])

with t_map:
    # --- POPOVER ACTION CENTER ---
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_data = df_raw[df_raw['Bakery Name'] == name].iloc[0]
        is_m = st.session_state.merchant_bakery == name
        
        with st.expander(f"📍 {name} {'(ADMIN)' if is_m else ''}", expanded=True):
            if is_m:
                # MERCHANT TOOLS
                ns = st.number_input("Update Stock", 0, 500, int(b_data['Stock']))
                t_f = st.text_input("Official Flavor", b_data['Fastelavnsbolle Type'])
                img = st.file_uploader("New Photo", type=['jpg','png'])
                if st.button("Update & Post Official Status"):
                    i_url = cloudinary.uploader.upload(img)['secure_url'] if img else b_data['Photo URL']
                    get_worksheet().append_row([name, t_f, i_url, b_data['Address'], b_data['lat'], b_data['lon'], 
                                              get_now_dk().strftime("%Y-%m-%d"), "Merchant", name, 5.0, 
                                              b_data['Price'], ns, get_now_dk().strftime("%H:%M"), "", "Restock!"], value_input_option='USER_ENTERED')
                    st.session_state.selected_bakery = None; st.cache_data.clear(); st.rerun()
            
            elif b_data['Stock'] <= 0:
                st.error("🚫 SOLD OUT")
                if st.button("Notify me on restock"): st.toast("Watchlist updated!")
                if st.button("Close"): st.session_state.selected_bakery = None; st.rerun()
            
            else:
                # USER THREE-STEP QUEUE
                if name not in st.session_state.arrival_times:
                    if st.button("🏁 I just arrived/joined the line", use_container_width=True):
                        st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}
                        st.rerun()
                elif st.session_state.arrival_times[name]["wait"] is None:
                    wait_so_far = (get_now_dk() - st.session_state.arrival_times[name]["start"]).seconds // 60
                    st.info(f"⏱️ You've been waiting for {wait_so_far} mins...")
                    if st.button("🛍️ Got my Bolle!", type="primary", use_container_width=True):
                        final_w = max(1, (get_now_dk() - st.session_state.arrival_times[name]["start"]).seconds // 60)
                        st.session_state.arrival_times[name]["wait"] = final_w; st.rerun()
                else:
                    st.success(f"Wait recorded: {st.session_state.arrival_times[name]['wait']} mins!")
                    with st.form("review_form"):
                        r_score = st.slider("Rating", 1.0, 5.0, 4.0)
                        r_comm = st.text_area("Your Review")
                        if st.form_submit_button("Post Review"):
                            get_worksheet().append_row([name, b_data['Fastelavnsbolle Type'], "", b_data['Address'], b_data['lat'], b_data['lon'],
                                                      get_now_dk().strftime("%Y-%m-%d"), "User", st.session_state.user_nickname,
                                                      r_score, b_data['Price'], b_data['Stock'], get_now_dk().strftime("%H:%M"),
                                                      "", r_comm, st.session_state.arrival_times[name]['wait']], value_input_option='USER_ENTERED')
                            del st.session_state.arrival_times[name]; st.session_state.selected_bakery = None
                            st.cache_data.clear(); st.rerun()

    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] == 0 else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name']).add_to(m)
    
    st_map = st_folium(m, width="100%", height=500)
    if st_map.get("last_object_clicked_tooltip"):
        if st.session_state.selected_bakery != st_map["last_object_clicked_tooltip"]:
            st.session_state.selected_bakery = st_map["last_object_clicked_tooltip"]
            st.rerun()

with t_stream:
    st.subheader("🧵 Recent Activity")
    stream_df = filtered.sort_values(by="Date", ascending=False)
    for i, r in stream_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['Bakery Name']}** {'✅' if r['Category']=='Merchant' else ''} | @{r['User']}")
            if r['Photo URL']: st.image(r['Photo URL'], width=300)
            st.write(f"⭐ {r['Rating']} | ⏳ {int(r['Wait Time'])} min wait")
            if r['Comment']: st.info(r['Comment'])
            if st.button("📍 View", key=f"s_{i}"):
                st.session_state.selected_bakery = r['Bakery Name']; st.rerun()

with t_top:
    st.header("🏆 2026 Leaderboard")
    valid = df_raw[df_raw['Rating'] > 0]
    
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🥇 Top Flavors")
        f_rank = valid.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].mean().sort_values(ascending=False).reset_index()
        st.dataframe(f_rank, use_container_width=True)
    
    with col_r:
        st.subheader("👑 Top Users")
        u_rank = valid['User'].value_counts().reset_index()
        for i, row in u_rank.iterrows():
            c1, c2 = st.columns([3, 1])
            c1.write(f"@{row['User']} ({row['count']} posts)")
            if c2.button("View", key=f"u_{i}"):
                st.session_state.user_filter = row['User']; st.rerun()

with t_help:
    st.header("❓ Help & FAQ")
    with st.expander("How do I update stock?"):
        st.write("Only verified merchants can update official stock. If you are a bakery owner, enter your secret key in the Settings.")
    with st.expander("How is wait time calculated?"):
        st.write("Click 'I've Arrived' when you join the line. Click 'Got my Bolle' when you pay. The app calculates the difference automatically!")
