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

df = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 3. SEARCH & SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Admin Tools")
    with st.expander("🆕 Register New Bakery"):
        n_name = st.text_input("Bakery Name")
        n_addr = st.text_input("Address (Copenhagen)")
        if st.button("Generate & Add"):
            from geopy.geocoders import Nominatim
            loc = Nominatim(user_agent="bollequest").geocode(n_addr)
            if loc:
                # GENERATE UNIQUE KEY
                new_key = str(random.randint(1000, 9999))
                # Append 15 columns
                get_worksheet().append_row([
                    n_name, "New Entry", "", n_addr, loc.latitude, loc.longitude, 
                    datetime.now().strftime("%Y-%m-%d"), "Bakery", "Admin", 
                    0, 0, 50, get_now_dk(), new_key, ""
                ], value_input_option='USER_ENTERED')
                st.success(f"Added! Secret Key for {n_name} is: {new_key}")
                st.info("Write this down and give it to the bakery!")
                st.cache_data.clear()
            else:
                st.error("Could not find address.")

st.title("🥯 BolleQuest")
search_q = st.text_input("🔍 Search flavor, bakery, or comments...", placeholder="e.g. 'Vegan' or 'Mocha'").strip().lower()

filtered = df_clean.copy()
if search_q:
    mask = (filtered['Fastelavnsbolle Type'].str.lower().str.contains(search_q, na=False) | 
            filtered['Bakery Name'].str.lower().str.contains(search_q, na=False) |
            filtered['Comment'].str.lower().str.contains(search_q, na=False))
    filtered = filtered[mask]

# --- 4. ACTION CENTER (Popover) ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_rows = df_clean[df_clean['Bakery Name'] == name]
    if not b_rows.empty:
        row = b_rows.iloc[0]
        with st.popover(f"📍 {name}", use_container_width=True):
            stock = int(b_rows['Stock'].max())
            l_upd = row.get('Last Updated', '--:--')
            
            c1, c2 = st.columns(2)
            c1.metric("Bakery Stock", "SOLD OUT" if stock <= 0 else f"{stock} left")
            c2.metric("Last Update", l_upd)
            
            st.link_button("🚗 Directions", f"https://www.google.com/maps/dir/?api=1&destination={row['lat']},{row['lon']}", use_container_width=True)
            
            st.divider()
            st.write("**📝 Community Check-in**")
            f_name = st.text_input("Flavor", placeholder="e.g. Classic Cream")
            f_comm = st.text_area("Live Comment", placeholder="e.g. 'Long queue but worth it!'", height=70)
            f_rate = st.slider("Rating", 1.0, 5.0, 4.0, 0.5)
            
            if st.button("Submit Update", use_container_width=True, type="primary"):
                get_worksheet().append_row([
                    name, f_name, "", row['Address'], row['lat'], row['lon'], 
                    datetime.now().strftime("%Y-%m-%d"), "User", "Guest", 
                    f_rate, 45, stock, get_now_dk(), row.get('Bakery Key', ''), f_comm
                ], value_input_option='USER_ENTERED')
                st.toast("Updated!")
                st.cache_data.clear(); time.sleep(1); st.rerun()

            if st.session_state.merchant_bakery == name:
                st.divider()
                st.write("🧑‍🍳 **Merchant: Restock**")
                new_s = st.number_input("Total Inventory Count", 0, 500, stock)
                if st.button("Update Stock"):
                    ws = get_worksheet()
                    cell = ws.find(name)
                    ws.update_cell(cell.row, 12, new_s)
                    ws.update_cell(cell.row, 13, get_now_dk())
                    st.cache_data.clear(); st.rerun()

# --- 5. TABS ---
t_map, t_buns, t_route, t_top, t_app = st.tabs(["📍 Map", "📜 Feed", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.iterrows():
        color = "red" if r['Stock'] <= 0 else "darkblue" if r['Bakery Name'] == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name'], icon=folium.Icon(color=color, icon="shopping-basket", prefix="fa")).add_to(m)
    st_folium(m, width="100%", height=400, key="main_map")

with t_buns:
    st.subheader("Community Live Feed")
    # Show entries with comments or ratings
    feed = filtered[filtered['Rating'] > 0].iloc[::-1]
    for i, r in enumerate(feed.itertuples()):
        with st.container(border=True):
            st.write(f"**{r._1}** — ⭐ {r.Rating}")
            st.caption(f"Flavor: {r._2} | {r._7}")
            if hasattr(r, '_15') and r._15: # Column O is _15
                st.info(f"💬 {r._15}")

with t_route:
    st.subheader("🚲 Efficient Route")
    stock_df = filtered[filtered['Stock'] > 0].copy()
    if not stock_df.empty:
        stock_df['dist'] = stock_df.apply(lambda r: geodesic((55.6761, 12.5683), (r['lat'], r['lon'])).km, axis=1)
        for i, r in enumerate(stock_df.sort_values('dist').head(5).itertuples()):
            st.write(f"{i+1}. **{r._1}** ({r.dist:.1f}km)")

with t_top:
    st.header("🏆 Rankings")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Top Flavors**")
        st.dataframe(df_clean[df_clean['Rating']>0].groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False).head(5))
    with c2:
        st.write("**Top Bakeries**")
        st.dataframe(df_clean[df_clean['Rating']>0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False).head(5))

with t_app:
    st.subheader("📲 Install & Login")
    st.write("iPhone: Share > Add to Home Screen")
    st.divider()
    st.header("🧑‍🍳 Merchant Login")
    k = st.text_input("Bakery Key", type="password")
    if k and 'Bakery Key' in df_clean.columns:
        match = df_clean[df_clean['Bakery Key'].astype(str) == k]
        if not match.empty:
            st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
            st.success(f"Authorized: {st.session_state.merchant_bakery}")
