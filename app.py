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
import numpy as np

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

# Initialize Session States
if "selected_bakery" not in st.session_state: st.session_state.selected_bakery = None
if "merchant_bakery" not in st.session_state: st.session_state.merchant_bakery = None
if "user_nickname" not in st.session_state: st.session_state.user_nickname = "Guest"
if "last_stock_check" not in st.session_state: st.session_state.last_stock_check = {}

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
    
    # Value Score Calculation (2 decimals)
    df['Value Score'] = df.apply(
        lambda r: round((float(r['Rating']) / float(r['Price']) * 100), 2) 
        if r['Price'] > 0 and r['Rating'] > 0 else 0.0, axis=1
    )
    return df

df_raw = load_data()

# --- 3. LIVE NOTIFICATIONS (Sold Out Alerts) ---
# We check if any bakery transitioned to 0 stock since the last load
for _, row in df_raw.iterrows():
    b_name = row['Bakery Name']
    current_stock = int(row['Stock'])
    prev_stock = st.session_state.last_stock_check.get(b_name, 1) # Default to 1 to avoid false alarms
    
    if current_stock == 0 and prev_stock > 0:
        st.toast(f"🚨 ALERT: {b_name} just SOLD OUT!", icon="🥐")
    
    st.session_state.last_stock_check[b_name] = current_stock

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🎯 Filter Quest")
    if st.button("🔄 Reset Filters"):
        st.session_state.max_p = 85
        st.session_state.min_r = 1.0
        st.rerun()

    max_p = st.slider("Max Price (DKK)", 0, 100, st.session_state.get('max_p', 85), key='max_p')
    min_r = st.slider("Min Rating", 1.0, 5.0, st.session_state.get('min_r', 1.0), 0.25, key='min_r')
    
    st.divider()
    st.info(f"👤 Profile: {st.session_state.user_nickname}")
    if st.session_state.merchant_bakery:
        st.success(f"🧑‍🍳 Merchant: {st.session_state.merchant_bakery}")

filtered = df_raw.copy()
filtered = filtered[(filtered['Price'] <= max_p) & (filtered['Rating'] >= min_r)]

# --- 5. ACTION CENTER ---
st.title("🥯 BolleQuest")
search = st.text_input("🔍 Search flavor, bakery, or vibes...", "").lower()
if search:
    filtered = filtered[filtered.astype(str).apply(lambda x: x.str.lower().str.contains(search)).any(axis=1)]

if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_row = df_raw[df_raw['Bakery Name'] == name].iloc[0]
    with st.popover(f"📍 {name} Menu & Check-in", use_container_width=True):
        if st.session_state.merchant_bakery == name:
            st.subheader("🧑‍🍳 Official Update")
            ns = st.number_input("Update Stock Count", 0, 500, int(b_row['Stock']))
            if st.button("Save Changes"):
                ws = get_worksheet(); cell = ws.find(name)
                ws.update_cell(cell.row, 12, ns)
                ws.update_cell(cell.row, 13, get_now_dk())
                st.cache_data.clear(); st.rerun()
        
        st.write("**📸 Share Your Review**")
        img = st.file_uploader("Upload Bun Photo", type=['jpg','png','jpeg'])
        t_f = st.text_input("What flavor?", value=b_row['Fastelavnsbolle Type'])
        t_c = st.text_area("Comment (max 280)", max_chars=280)
        
        rating_opts = [round(x, 2) for x in np.arange(1, 5.25, 0.25).tolist()]
        t_r = st.select_slider("Rating", options=rating_opts, value=4.0)
        
        if st.button("Post to Stream 🚀", use_container_width=True, type="primary"):
            with st.spinner("Uploading..."):
                i_url = cloudinary.uploader.upload(img)['secure_url'] if img else ""
                is_m = "Merchant" if st.session_state.merchant_bakery == name else "User Report"
                
                get_worksheet().append_row([
                    str(name), str(t_f), str(i_url), str(b_row['Address']), 
                    float(b_row['lat']), float(b_row['lon']), datetime.now().strftime("%Y-%m-%d"), 
                    str(is_m), str(st.session_state.user_nickname), float(t_r), 
                    float(b_row['Price']), int(b_row['Stock']), str(get_now_dk()), 
                    str(b_row.get('Bakery Key','')), str(t_c)
                ], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- 6. TABS ---
t_map, t_feed, t_top, t_app = st.tabs(["📍 Map", "🧵 Stream", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        col = "blue" if r['Bakery Name'] == st.session_state.selected_bakery else ("red" if r['Stock'] <= 0 else "green")
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name'], icon=folium.Icon(color=col)).add_to(m)
    
    m_data = st_folium(m, width="100%", height=450, key="main_map")
    if m_data and m_data.get("last_object_clicked_tooltip"):
        clicked = m_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked; st.rerun()

with t_feed:
    st.subheader("🧵 Community Stream")
    stream = filtered.sort_values(by=['Date', 'Last Updated'], ascending=False)
    for i, r in stream.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['Bakery Name']}** {'✅' if r['Category']=='Merchant' else ''} <span style='color:gray;'>@{r['User']}</span>", unsafe_allow_html=True)
            if r['Photo URL']: st.image(r['Photo URL'], use_container_width=True)
            st.write(f"**{r['Fastelavnsbolle Type']}** | ⭐ {r['Rating']}")
            if r['Comment']: st.info(r['Comment'])
            if st.button("📍 View on Map", key=f"f_{i}"):
                st.session_state.selected_bakery = r['Bakery Name']; st.rerun()

with t_top:
    st.header("🏆 The 2026 Rankings")
    mode = st.radio("Display:", ["Flavours by Bakery", "Bakeries & Flavours", "Value Score", "Users"], horizontal=True)
    valid = df_raw[df_raw['Rating'] > 0].copy()
    
    if mode == "Flavours by Bakery":
        flavor_rank = valid.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].mean().sort_values(ascending=False).reset_index()
        st.dataframe(flavor_rank, use_container_width=True, hide_index=True)

    elif mode == "Bakeries & Flavours":
        bakery_rank = valid.groupby('Bakery Name').agg({
            'Rating': 'mean',
            'Fastelavnsbolle Type': lambda x: ", ".join(set(x)),
            'Stock': 'max'
        }).sort_values('Rating', ascending=False).reset_index()
        bakery_rank['Status'] = bakery_rank['Stock'].apply(lambda x: "✅ IN STOCK" if x > 0 else "🚫 SOLD OUT")
        st.dataframe(bakery_rank[['Bakery Name', 'Rating', 'Status', 'Fastelavnsbolle Type']], use_container_width=True, hide_index=True)

    elif mode == "Value Score":
        val_df = valid[['Bakery Name', 'Fastelavnsbolle Type', 'Price', 'Rating', 'Value Score']].sort_values('Value Score', ascending=False)
        st.dataframe(val_df, use_container_width=True, hide_index=True)

    elif mode == "Users":
        st.dataframe(valid['User'].value_counts().reset_index().rename(columns={'User': 'Hobbyist', 'count': 'Check-ins'}), use_container_width=True, hide_index=True)

with t_app:
    st.subheader("👤 Profile Settings")
    new_nick = st.text_input("Edit Nickname", value=st.session_state.user_nickname)
    if st.button("Save Profile Name"):
        st.session_state.user_nickname = new_nick
        st.toast(f"Profile updated to @{new_nick}!", icon="👤")
    
    st.divider()
    st.subheader("🧑‍🍳 Bakery Dashboard")
    if st.session_state.merchant_bakery:
        st.info(f"Authorized for: {st.session_state.merchant_bakery}")
        if st.button("Switch to User Mode"):
            st.session_state.merchant_bakery = None; st.rerun()
    else:
        k_in = st.text_input("Enter Bakery Secret Key", type="password")
        if k_in:
            match = df_raw[df_raw['Bakery Key'].astype(str) == k_in]
            if not match.empty:
                st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                st.toast("Success: Merchant access granted!", icon="🔑")
                st.rerun()
