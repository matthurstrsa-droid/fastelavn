import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from datetime import datetime
import pytz
import time
import cloudinary.uploader
import numpy as np # Needed for the 0.25 scale

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

if "selected_bakery" not in st.session_state: st.session_state.selected_bakery = None
if "merchant_bakery" not in st.session_state: st.session_state.merchant_bakery = None
if "user_nickname" not in st.session_state: st.session_state.user_nickname = "Guest"

# --- 2. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    df = pd.DataFrame(get_worksheet().get_all_records())
    df.columns = [c.strip() for c in df.columns]
    for col in ['lat', 'lon', 'Rating', 'Price', 'Stock']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Value Score'] = df.apply(lambda r: (float(r['Rating']) / float(r['Price']) * 100) if r['Price'] > 0 and r['Rating'] > 0 else 0, axis=1)
    return df

df_raw = load_data()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🎯 Filter Quest")
    if st.button("🔄 Clear All Filters"):
        st.session_state.max_p = 85
        st.session_state.min_r = 0.0
        st.rerun()

    max_p = st.slider("Max Price (DKK)", 0, 100, st.session_state.get('max_p', 85), key='max_p')
    # Adjusted Rating Slider to 0.25 increments
    min_r = st.slider("Min Rating", 1.0, 5.0, st.session_state.get('min_r', 1.0), 0.25, key='min_r')
    
    st.divider()
    st.info(f"👤 Profile: {st.session_state.user_nickname}")
    if st.session_state.merchant_bakery:
        st.success(f"🧑‍🍳 Merchant: {st.session_state.merchant_bakery}")

filtered = df_raw.copy()
filtered = filtered[(filtered['Price'] <= max_p) & (filtered['Rating'] >= min_r)]

# --- 4. SEARCH & ACTION CENTER ---
st.title("🥯 BolleQuest")
search = st.text_input("🔍 Search flavor, bakery, or vibes...", "").lower()
if search:
    filtered = filtered[filtered['Bakery Name'].str.lower().str.contains(search) | 
                        filtered['Fastelavnsbolle Type'].str.lower().str.contains(search)]

if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    row = df_raw[df_raw['Bakery Name'] == name].iloc[0]
    with st.popover(f"📍 Open {name} Menu", use_container_width=True):
        if st.session_state.merchant_bakery == name:
            st.subheader("🧑‍🍳 Merchant Tools")
            ns = st.number_input("Update Stock", 0, 500, int(row['Stock']))
            if st.button("Save Inventory"):
                ws = get_worksheet()
                cell = ws.find(name)
                ws.update_cell(cell.row, 12, ns)
                ws.update_cell(cell.row, 13, get_now_dk())
                st.cache_data.clear(); st.rerun()
        
        st.write("**📸 Share Check-in**")
        img = st.file_uploader("Upload Bun Photo", type=['jpg','png','jpeg'])
        t_f = st.text_input("What flavor?", value=row['Fastelavnsbolle Type'])
        t_c = st.text_area("Comment", max_chars=280)
        
        # 0.25 Scale Rating for Check-in
        rating_options = [round(x, 2) for x in np.arange(1, 5.25, 0.25).tolist()]
        t_r = st.select_slider("Rating (1-5)", options=rating_options, value=4.0)
        
        if st.button("Post to Stream 🚀", use_container_width=True, type="primary"):
            with st.spinner("Uploading..."):
                i_url = cloudinary.uploader.upload(img)['secure_url'] if img else ""
                is_m = "Merchant" if st.session_state.merchant_bakery == name else "User Report"
                
                # We wrap everything in str() or float() to prevent JSON Serializer errors
                get_worksheet().append_row([
                    str(name), 
                    str(t_f), 
                    str(i_url), 
                    str(row['Address']), 
                    float(row['lat']), 
                    float(row['lon']),
                    datetime.now().strftime("%Y-%m-%d"), 
                    str(is_m), 
                    str(st.session_state.user_nickname),
                    float(t_r), 
                    float(row['Price']), 
                    int(row['Stock']), 
                    str(get_now_dk()), 
                    str(row.get('Bakery Key','')), 
                    str(t_c)
                ], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- 5. TABS ---
t_map, t_feed, t_top, t_app = st.tabs(["📍 Map", "🧵 Stream", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        col = "blue" if r['Bakery Name'] == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name'], icon=folium.Icon(color=col)).add_to(m)
    
    map_data = st_folium(m, width="100%", height=450, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t_feed:
    st.subheader("🧵 Live Stream")
    stream_df = filtered.sort_values(by=['Date', 'Last Updated'], ascending=False)
    for i, r in stream_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['Bakery Name']}** {'✅' if r['Category']=='Merchant' else ''} @{r['User']}")
            if r['Photo URL']: st.image(r['Photo URL'], use_container_width=True)
            st.write(f"**{r['Fastelavnsbolle Type']}** | ⭐ {r['Rating']}")
            if r['Comment']: st.info(r['Comment'])
            if st.button("📍 View", key=f"j_{i}"):
                st.session_state.selected_bakery = r['Bakery Name']; st.rerun()

with t_top:
    st.header("🏆 Leaderboards")
    mode = st.radio("Rank by:", ["Flavours", "Bakeries", "Value", "Users"], horizontal=True)
    valid = df_raw[df_raw['Rating'] > 0]
    if mode == "Flavours":
        st.dataframe(valid.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False))
    elif mode == "Bakeries":
        st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False))
    elif mode == "Value":
        st.dataframe(valid[['Bakery Name', 'Value Score']].sort_values('Value Score', ascending=False), hide_index=True)
    elif mode == "Users":
        st.dataframe(valid['User'].value_counts())

with t_app:
    st.subheader("👤 User Profile")
    st.session_state.user_nickname = st.text_input("Nickname", value=st.session_state.user_nickname)
    
    st.divider()
    st.subheader("🧑‍🍳 Bakery Dashboard")
    if st.session_state.merchant_bakery:
        st.info(f"Managing: {st.session_state.merchant_bakery}")
        if st.button("Log Out of Bakery Mode"):
            st.session_state.merchant_bakery = None
            st.rerun()
    else:
        key_in = st.text_input("Bakery Key", type="password")
        if key_in:
            match = df_raw[df_raw['Bakery Key'].astype(str) == key_in]
            if not match.empty:
                st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                st.success("Authorized!"); st.rerun()
