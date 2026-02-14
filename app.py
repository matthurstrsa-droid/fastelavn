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

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

# Initialize Session States for Persistence
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
    # Value Index Calculation: (Rating / Price) * 100
    df['Value Score'] = df.apply(lambda r: (r['Rating'] / r['Price'] * 100) if r['Price'] > 0 and r['Rating'] > 0 else 0, axis=1)
    return df

df_raw = load_data()

# --- 3. SIDEBAR FILTERS ---
with st.sidebar:
    st.title("🎯 Filter Quest")
    
    # Reset Logic
    if st.button("🔄 Clear All Filters", use_container_width=True):
        st.session_state.max_p = 85
        st.session_state.min_r = 0.0
        st.session_state.only_s = False
        st.rerun()

    max_p = st.slider("Max Price (DKK)", 0, 100, st.session_state.get('max_p', 85), key='max_p')
    min_r = st.slider("Min Rating", 0.0, 5.0, st.session_state.get('min_r', 0.0), 0.5, key='min_r')
    only_stock = st.checkbox("In Stock Only", value=st.session_state.get('only_s', False), key='only_s')
    
    st.divider()
    st.info(f"👤 Profile: {st.session_state.user_nickname}")
    if st.session_state.merchant_bakery:
        st.success(f"🧑‍🍳 Merchant: {st.session_state.merchant_bakery}")

# Global Filter Application
filtered = df_raw.copy()
filtered = filtered[(filtered['Price'] <= max_p) & (filtered['Rating'] >= min_r)]
if only_stock: filtered = filtered[filtered['Stock'] > 0]

# --- 4. TOP INTERFACE & SEARCH ---
st.title("🥯 BolleQuest")

# Focused Bakery Header
if st.session_state.selected_bakery:
    c_clear1, c_clear2 = st.columns([3, 1])
    c_clear1.warning(f"Focused on: {st.session_state.selected_bakery}")
    if c_clear2.button("Show All pins ✕", use_container_width=True):
        st.session_state.selected_bakery = None
        st.rerun()

search = st.text_input("🔍 Search flavor, bakery, or vibes...", "").lower()
if search:
    filtered = filtered[filtered['Bakery Name'].str.lower().str.contains(search) | 
                        filtered['Fastelavnsbolle Type'].str.lower().str.contains(search) |
                        filtered['Comment'].str.lower().str.contains(search)]

# --- 5. ACTION CENTER (The Popover) ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    bakery_data = df_raw[df_raw['Bakery Name'] == name]
    if not bakery_data.empty:
        row = bakery_data.iloc[0]
        with st.popover(f"📍 Open {name} Menu", use_container_width=True):
            stock = int(row['Stock'])
            
            # MERCHANT TOOLS
            if st.session_state.merchant_bakery == name:
                st.subheader("🧑‍🍳 Official Controls")
                ns = st.number_input("Current Stock Count", 0, 500, stock)
                if st.button("Update Inventory", use_container_width=True):
                    ws = get_worksheet()
                    cell = ws.find(name)
                    ws.update_cell(cell.row, 12, ns) # Stock
                    ws.update_cell(cell.row, 13, get_now_dk()) # Last Updated
                    st.cache_data.clear(); st.rerun()
                st.divider()
            
            # POSTING SECTION (Users & Merchants)
            st.write("**📸 Share an Update / Add Flavor**")
            img = st.file_uploader("Add Photo", type=['jpg','png','jpeg'])
            t_f = st.text_input("Flavor", value=row['Fastelavnsbolle Type'], placeholder="e.g. Mocha")
            t_c = st.text_area("Live Comment", placeholder="Queue? Flavor details?", max_chars=280)
            t_r = st.select_slider("Rating", options=[1,2,3,4,5], value=4)
            
            if st.button("Post to Stream 🚀", use_container_width=True, type="primary"):
                with st.spinner("Posting..."):
                    i_url = cloudinary.uploader.upload(img)['secure_url'] if img else ""
                    is_m = "Merchant" if st.session_state.merchant_bakery == name else "User Report"
                    get_worksheet().append_row([
                        name, t_f, i_url, row['Address'], row['lat'], row['lon'],
                        datetime.now().strftime("%Y-%m-%d"), is_m, st.session_state.user_nickname,
                        t_r, row['Price'], stock, get_now_dk(), row.get('Bakery Key',''), t_c
                    ], value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.rerun()

# --- 6. TABS ---
t_map, t_feed, t_route, t_top, t_app = st.tabs(["📍 Map", "🧵 Stream", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    # Build Map
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        # Color Logic: Selected = Blue, Sold Out = Red, Normal = Green
        if r['Bakery Name'] == st.session_state.selected_bakery: col = "blue"
        elif r['Stock'] <= 0: col = "red"
        else: col = "green"
        
        folium.Marker(
            [r['lat'], r['lon']], 
            tooltip=r['Bakery Name'],
            icon=folium.Icon(color=col, icon="shopping-basket", prefix="fa")
        ).add_to(m)
    
    # Capture Clicks and Sync with Action Center
    map_data = st_folium(m, width="100%", height=450, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked_name = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked_name:
            st.session_state.selected_bakery = clicked_name
            st.rerun()

with t_feed:
    # Pulse Stats Header
    today = datetime.now().strftime("%Y-%m-%d")
    today_df = df_raw[df_raw['Date'] == today]
    c1, c2, c3 = st.columns(3)
    c1.metric("Spotted Today", len(today_df))
    c2.metric("Avg Rating", f"{today_df['Rating'].mean():.1f}" if not today_df.empty else "0.0")
    c3.metric("Live Shops", df_raw[df_raw['Stock'] > 0]['Bakery Name'].nunique())
    st.divider()

    # The Twitter-style Stream (Latest first)
    stream_df = filtered.sort_values(by=['Date', 'Last Updated'], ascending=False)
    for i, r in stream_df.iterrows():
        with st.container(border=True):
            is_off = r['Category'] == 'Merchant'
            u_name = r['User'] if r['User'] else "guest"
            
            # Post Header with Merchant Badge
            st.markdown(f"**{r['Bakery Name']}** {'✅' if is_off else ''} <span style='color:gray;'>@{u_name}</span>", unsafe_allow_html=True)
            
            # Content
            if r['Photo URL']: st.image(r['Photo URL'], use_container_width=True)
            st.write(f"**{r['Fastelavnsbolle Type']}** | {'★'*int(r['Rating'])}")
            if r['Comment']: st.info(f"💬 {r['Comment']}")
            
            st.caption(f"Spotted at {r['Last Updated']} • {r['Date']}")
            if st.button("📍 View on Map", key=f"jump_{i}"):
                st.session_state.selected_bakery = r['Bakery Name']; st.rerun()

with t_route:
    st.subheader("🚲 Efficient Bun Run")
    route_df = filtered[filtered['Stock'] > 0].copy()
    if not route_df.empty:
        # Distance calculation relative to CPH city center
        route_df['dist'] = route_df.apply(lambda r: geodesic((55.6761, 12.5683), (r['lat'], r['lon'])).km, axis=1)
        for i, (idx, r) in enumerate(route_df.sort_values('dist').head(5).iterrows()):
            st.write(f"{i+1}. **{r['Bakery Name']}** ({r['dist']:.1f}km)")
    else:
        st.info("No in-stock bakeries match your filters.")

with t_top:
    st.header("🏆 The Leaderboard")
    mode = st.radio("Rank by:", ["Flavours", "Bakeries", "Value", "Users"], horizontal=True)
    valid = df_raw[df_raw['Rating'] > 0]
    
    if mode == "Flavours":
        st.dataframe(valid.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False), use_container_width=True)
    elif mode == "Bakeries":
        st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False), use_container_width=True)
    elif mode == "Value":
        # Sort by Value Score (Rating/Price Index)
        st.dataframe(valid[['Bakery Name', 'Fastelavnsbolle Type', 'Value Score']].sort_values('Value Score', ascending=False), use_container_width=True, hide_index=True)
    elif mode == "Users":
        st.dataframe(valid['User'].value_counts().reset_index().rename(columns={'count':'Spotted'}), use_container_width=True, hide_index=True)

with t_app:
    st.subheader("👤 User Profile")
    new_nick = st.text_input("Choose a Nickname", value=st.session_state.user_nickname)
    if st.button("Save Profile Name"):
        st.session_state.user_nickname = new_nick; st.success("Profile Updated!")
    
    st.divider()
    st.subheader("🧑‍🍳 Bakery Dashboard")
    key_in = st.text_input("Enter Secret Bakery Key", type="password")
    if key_in:
        match = df_raw[df_raw['Bakery Key'].astype(str) == key_in]
        if not match.empty:
            st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
            st.success(f"Managing: {st.session_state.merchant_bakery}")
        else:
            st.error("Invalid Key")
