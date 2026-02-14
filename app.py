import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from datetime import datetime
import pytz
import random
import time
import cloudinary.uploader

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

# Initialize Session States
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
    # Calculate Value Score
    df['Value Score'] = df.apply(lambda r: (r['Rating'] / r['Price'] * 100) if r['Price'] > 0 and r['Rating'] > 0 else 0, axis=1)
    return df

df_raw = load_data()

# --- 3. SIDEBAR FILTERS ---
with st.sidebar:
    st.title("🎯 Filter Quest")
    max_p = st.slider("Max Price (DKK)", 0, 100, 75)
    min_r = st.slider("Min Rating", 0.0, 5.0, 0.0, 0.5)
    only_stock = st.checkbox("In Stock Only", value=False)
    st.divider()
    st.caption(f"Logged in as: {st.session_state.user_nickname}")
    if st.session_state.merchant_bakery:
        st.success(f"Merchant: {st.session_state.merchant_bakery}")

# Apply Logic
filtered = df_raw.copy()
filtered = filtered[(filtered['Price'] <= max_p) & (filtered['Rating'] >= min_r)]
if only_stock: filtered = filtered[filtered['Stock'] > 0]

# --- 4. SEARCH & ACTION CENTER ---
st.title("🥯 BolleQuest")
search = st.text_input("🔍 Search flavor or bakery...", "").lower()
if search:
    filtered = filtered[filtered['Bakery Name'].str.lower().str.contains(search) | 
                        filtered['Fastelavnsbolle Type'].str.lower().str.contains(search) |
                        filtered['Comment'].str.lower().str.contains(search)]

if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    row = df_raw[df_raw['Bakery Name'] == name].iloc[0]
    with st.popover(f"📍 {name}", use_container_width=True):
        if st.session_state.merchant_bakery == name:
            st.subheader("🧑‍🍳 Merchant Update")
            ns = st.number_input("New Stock Count", 0, 500, int(row['Stock']))
            if st.button("Save Stock"):
                ws = get_worksheet()
                c = ws.find(name)
                ws.update_cell(c.row, 12, ns) # Stock
                ws.update_cell(c.row, 13, get_now_dk()) # Time
                st.cache_data.clear(); st.rerun()
        
        st.write("**📸 Check-in**")
        img = st.file_uploader("Add Photo", type=['jpg','png'])
        t_f = st.text_input("Flavor", value=row['Fastelavnsbolle Type'])
        t_c = st.text_area("Comment", max_chars=280)
        t_r = st.select_slider("Rating", options=[1,2,3,4,5], value=4)
        
        if st.button("Post 🚀", use_container_width=True, type="primary"):
            i_url = cloudinary.uploader.upload(img)['secure_url'] if img else ""
            cat = "Merchant" if st.session_state.merchant_bakery == name else "User Report"
            get_worksheet().append_row([
                name, t_f, i_url, row['Address'], row['lat'], row['lon'],
                datetime.now().strftime("%Y-%m-%d"), cat, st.session_state.user_nickname,
                t_r, row['Price'], row['Stock'], get_now_dk(), row.get('Bakery Key',''), t_c
            ], value_input_option='USER_ENTERED')
            st.cache_data.clear(); st.rerun()

# --- 5. TABS ---
t_map, t_feed, t_route, t_top, t_app = st.tabs(["📍 Map", "🧵 Stream", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat','lon']).iterrows():
        c = "red" if r['Stock'] <= 0 else "blue" if r['Bakery Name'] == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name']).add_to(m)
    st_folium(m, width="100%", height=400)

with t_feed:
    st.subheader("🧵 Live Stream")
    for i, r in filtered.sort_values(['Date','Last Updated'], ascending=False).iterrows():
        with st.container(border=True):
            is_m = r['Category'] == 'Merchant'
            st.markdown(f"**{r['Bakery Name']}** {'✅' if is_m else ''} @{r['User']}")
            if r['Photo URL']: st.image(r['Photo URL'], use_container_width=True)
            st.write(f"**{r['Fastelavnsbolle Type']}** | {'★'*int(r['Rating'])}")
            if r['Comment']: st.info(r['Comment'])
            if st.button("View", key=f"f_{i}"):
                st.session_state.selected_bakery = r['Bakery Name']; st.rerun()

with t_top:
    st.header("🏆 Rankings")
    mode = st.radio("Toggle:", ["Flavours", "Bakeries", "Value", "Users"], horizontal=True)
    valid = df_raw[df_raw['Rating'] > 0]
    if mode == "Flavours":
        st.dataframe(valid.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False), use_container_width=True)
    elif mode == "Bakeries":
        st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False), use_container_width=True)
    elif mode == "Value":
        st.dataframe(valid[['Bakery Name','Value Score']].sort_values('Value Score', ascending=False), use_container_width=True)
    elif mode == "Users":
        st.dataframe(valid['User'].value_counts(), use_container_width=True)

with t_app:
    st.subheader("👤 User Profile")
    nick = st.text_input("Choose Nickname", value=st.session_state.user_nickname)
    if st.button("Save Profile"):
        st.session_state.user_nickname = nick; st.success("Saved!")
    
    st.divider()
    st.subheader("🧑‍🍳 Merchant Login")
    k_in = st.text_input("Secret Key", type="password")
    if k_in:
        match = df_raw[df_raw['Bakery Key'].astype(str) == k_in]
        if not match.empty:
            st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
            st.success(f"Logged in: {st.session_state.merchant_bakery}")
