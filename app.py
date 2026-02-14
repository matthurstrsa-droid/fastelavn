import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from folium.plugins import Geocoder
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import pytz
import time

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

# Session State
if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

# --- 2. DATA ENGINE ---
@st.cache_resource
def get_gs_client():
    creds = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    ws = get_worksheet()
    df = pd.DataFrame(ws.get_all_records())
    # Standardize column types
    num_cols = ['Rating', 'Price', 'lat', 'lon', 'Stock']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 3. MAIN UI & SEARCH ---
st.title("🥯 BolleQuest")

search = st.text_input("🔍 Search flavor, bakery, or area...", placeholder="e.g. 'Semla' or 'Nørrebro'")
filtered = df_clean.copy()
if search:
    filtered = filtered[filtered.apply(lambda row: search.lower() in row.astype(str).str.lower().values, axis=1)]

# --- 4. THE ACTION CENTER (Popover) ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_data = df_clean[df_clean['Bakery Name'] == name]
    row = b_data.iloc[0]
    
    with st.popover(f"📍 {name}", use_container_width=True):
        # Stock & Time
        stock = int(b_data['Stock'].max())
        l_upd = row.get('Last Updated', '--:--')
        
        c1, c2 = st.columns(2)
        c1.metric("Stock", f"{stock} left", delta=None)
        c2.metric("Updated", l_upd, delta=None)
        
        st.link_button("🚗 Get Directions", f"https://www.google.com/maps/dir/?api=1&destination={row['lat']},{row['lon']}", use_container_width=True)
        
        st.divider()
        if st.button("🚨 Report SOLD OUT", use_container_width=True, type="secondary"):
            ws = get_worksheet()
            cell = ws.find(name)
            ws.update_cell(cell.row, 12, 0) # Stock
            ws.update_cell(cell.row, 13, get_now_dk()) # Last Updated
            st.toast("Status updated. Thanks for helping!")
            st.cache_data.clear(); time.sleep(1); st.rerun()

        if st.button("Close ✕", use_container_width=True):
            st.session_state.selected_bakery = None; st.rerun()

# --- 5. TABS ---
t_map, t_list, t_gallery, t_route, t_leader, t_install = st.tabs(["📍 Map", "📜 Buns", "📸 Gallery", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for b_name in filtered['Bakery Name'].unique():
        data = filtered[filtered['Bakery Name'] == b_name]
        r = data.iloc[0]
        # Icon color based on stock
        ic_color = "red" if data['Stock'].max() <= 0 else "darkblue" if b_name == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=b_name, icon=folium.Icon(color=ic_color, icon="shopping-basket", prefix="fa")).add_to(m)
    
    map_res = st_folium(m, width="100%", height=400, key="main_map")
    if map_res and map_res.get("last_object_clicked_tooltip"):
        st.session_state.selected_bakery = map_res["last_object_clicked_tooltip"]
        st.rerun()

with t_list:
    st.subheader("Buns by Rating")
    # Only show items that have been rated
    buns = filtered[filtered['Rating'] > 0].sort_values('Rating', ascending=False)
    for _, r in buns.iterrows():
        if st.button(f"⭐ {r['Rating']} | {r['Fastelavnsbolle Type']} @ {r['Bakery Name']}", use_container_width=True):
            st.session_state.selected_bakery = r['Bakery Name']
            st.rerun()

with t_leader:
    st.subheader("🏆 Top Contributors")
    st.write("Users with the most ratings submitted:")
    # Grouping by 'User' column
    if 'User' in df.columns:
        leaderboard = df[df['Rating'] > 0.1]['User'].value_counts().reset_index()
        leaderboard.columns = ['User', 'Total Ratings']
        st.table(leaderboard.head(10))
    else:
        st.info("No user data available for leaderboard.")

with t_route:
    st.subheader("🚲 The Optimal Route")
    # Finds 5 closest bakeries that ARE in stock
    in_stock = filtered[filtered['Stock'] > 0]
    if not in_stock.empty:
        # Distance logic
        base = (55.6761, 12.5683) # City center
        in_stock = in_stock.copy()
        in_stock['dist'] = in_stock.apply(lambda r: geodesic(base, (r['lat'], r['lon'])).km, axis=1)
        route = in_stock.sort_values('dist').head(5)
        for i, r in enumerate(route.itertuples()):
            st.write(f"{i+1}. **{r._1}** — {r.dist:.1f}km away")
    else:
        st.warning("All buns in this area are currently sold out!")

with t_install:
    st.markdown("### 📲 Use it like an App")
    st.write("**iOS:** Share > Add to Home Screen")
    st.write("**Android:** Menu > Install App")
