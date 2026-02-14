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

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None
if "merchant_bakery" not in st.session_state:
    st.session_state.merchant_bakery = None

# --- 2. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    try:
        return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)
    except:
        st.error("🚫 Google Sheets Access Denied. Check Share settings!")
        st.stop()

@st.cache_data(ttl=2)
def load_data():
    df = pd.DataFrame(get_worksheet().get_all_records())
    df.columns = [c.strip() for c in df.columns]
    num_cols = ['lat', 'lon', 'Rating', 'Price', 'Stock']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df_clean = load_data()

# --- 3. HEADER & SEARCH ---
st.title("🥯 BolleQuest")
search_q = st.text_input("🔍 Search flavor, bakery, or comments...", placeholder="e.g. 'Vegan'").strip().lower()

filtered = df_clean.copy()
if search_q:
    mask = (filtered['Fastelavnsbolle Type'].str.lower().str.contains(search_q, na=False) | 
            filtered['Bakery Name'].str.lower().str.contains(search_q, na=False) |
            filtered['Comment'].str.lower().str.contains(search_q, na=False))
    filtered = filtered[mask]

# --- 4. ACTION CENTER (Popover Logic) ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_rows = df_clean[df_clean['Bakery Name'] == name]
    if not b_rows.empty:
        row = b_rows.iloc[0]
        with st.popover(f"📍 {name}", use_container_width=True):
            stock = int(row['Stock'])
            
            c1, c2 = st.columns(2)
            c1.metric("Stock", "SOLD OUT" if stock <= 0 else f"{stock} left")
            c2.metric("Updated", row.get('Last Updated', '--:--'))
            
            # --- POST TO STREAM SECTION ---
            st.write("**🚀 Post to Stream**")
            t_flav = st.text_input("Flavor", value=row['Fastelavnsbolle Type'])
            t_comm = st.text_area("Comment", placeholder="Queue length? Flavor vibes?", max_chars=280)
            t_rate = st.select_slider("Rating", options=[1, 2, 3, 4, 5], value=4)
            
            if st.button("Post 🚀", use_container_width=True, type="primary"):
                get_worksheet().append_row([
                    name, t_flav, "", row['Address'], row['lat'], row['lon'],
                    datetime.now().strftime("%Y-%m-%d"), "User", "Guest",
                    t_rate, 45, stock, get_now_dk(), row.get('Bakery Key', ''), t_comm
                ], value_input_option='USER_ENTERED')
                st.toast("Posted!")
                st.cache_data.clear(); time.sleep(1); st.rerun()

            if st.session_state.merchant_bakery == name:
                st.divider()
                new_s = st.number_input("Merchant: Inventory", 0, 500, stock)
                if st.button("Update Stock"):
                    ws = get_worksheet()
                    cell = ws.find(name)
                    ws.update_cell(cell.row, 12, new_s)
                    ws.update_cell(cell.row, 13, get_now_dk())
                    st.cache_data.clear(); st.rerun()
            
            if st.button("Close ✕"):
                st.session_state.selected_bakery = None; st.rerun()

# --- 5. TABS DEFINITION ---
t_map, t_buns, t_route, t_top, t_app = st.tabs(["📍 Map", "🧵 Stream", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] <= 0 else "darkblue" if r['Bakery Name'] == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name'], icon=folium.Icon(color=color, icon="shopping-basket", prefix="fa")).add_to(m)
    
    m_res = st_folium(m, width="100%", height=400, key="main_map")
    if m_res and m_res.get("last_object_clicked_tooltip"):
        st.session_state.selected_bakery = m_res["last_object_clicked_tooltip"]
        st.rerun()

with t_buns:
    # --- Pulse Header ---
    today_activity = df_clean[df_clean['Date'] == datetime.now().strftime("%Y-%m-%d")]
    c1, c2, c3 = st.columns(3)
    c1.metric("Spotted Today", f"{len(today_activity)}")
    c2.metric("City Avg", f"{today_activity['Rating'].mean():.1f}" if not today_activity.empty else "0.0")
    c3.metric("Live Bakeries", f"{df_clean[df_clean['Stock'] > 0]['Bakery Name'].nunique()}")
    st.divider()

    # --- Timeline Stream ---
    timeline = filtered.sort_values(by=['Date', 'Last Updated'], ascending=False)
    for i, (idx, row) in enumerate(timeline.iterrows()):
        with st.container(border=True):
            st.markdown(f"**{row['Bakery Name']}** <span style='color:gray;'>@guest</span>", unsafe_allow_html=True)
            st.markdown(f"**{row['Fastelavnsbolle Type']}** — {'★'*int(row['Rating'])}")
            if row['Comment']: st.info(f"💬 {row['Comment']}")
            st.caption(f"Spotted at {row['Last Updated']}")
            if st.button("Map 📍", key=f"btn_{i}"):
                st.session_state.selected_bakery = row['Bakery Name']; st.rerun()

with t_route:
    st.subheader("🚲 Efficient Route")
    stock_df = filtered[filtered['Stock'] > 0].copy()
    if not stock_df.empty:
        stock_df['dist'] = stock_df.apply(lambda r: geodesic((55.6761, 12.5683), (r['lat'], r['lon'])).km, axis=1)
        for i, (idx, r) in enumerate(stock_df.sort_values('dist').head(5).iterrows()):
            st.write(f"{i+1}. **{r['Bakery Name']}** ({r['dist']:.1f}km)")

with t_top:
    st.header("🏆 Rankings")
    c1, c2 = st.columns(2)
    valid = df_clean[df_clean['Rating'] > 0]
    with c1:
        st.write("Top Flavors")
        st.dataframe(valid.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False).head(5))
    with c2:
        st.write("Top Bakeries")
        st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False).head(5))

with t_app:
    st.header("🧑‍🍳 Bakery Login")
    k = st.text_input("Bakery Key", type="password")
    if k:
        match = df_clean[df_clean['Bakery Key'].astype(str) == k]
        if not match.empty:
            st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
            st.success(f"Managing: {st.session_state.merchant_bakery}")
