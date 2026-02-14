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
import cloudinary.uploader
import time

# --- 1. CORE CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None
if "is_merchant" not in st.session_state:
    st.session_state.is_merchant = False

# --- 2. CONNECTIONS ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

# Cloudinary Config
try:
    cloudinary.config(
        cloud_name = st.secrets["cloudinary"]["cloud_name"],
        api_key = st.secrets["cloudinary"]["api_key"],
        api_secret = st.secrets["cloudinary"]["api_secret"],
        secure = True
    )
except:
    st.error("Cloudinary Secret Error. Photo uploads will fail.")

@st.cache_data(ttl=2)
def load_data():
    ws = get_worksheet()
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.strip() for c in df.columns]
    # Enforce numeric types
    num_cols = ['Rating', 'Price', 'lat', 'lon', 'Stock']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 3. SIDEBAR & SEARCH ---
with st.sidebar:
    st.header("🔍 Controls")
    search_q = st.text_input("Fuzzy Search (Flavor/Bakery)")
    
    st.divider()
    st.header("🧑‍🍳 Merchant Access")
    m_key = st.text_input("Bakery Key", type="password")
    if m_key == st.secrets.get("general", {}).get("bakery_key", ""):
        st.session_state.is_merchant = True
        st.success("Merchant Mode On")
    else:
        st.session_state.is_merchant = False

    st.divider()
    with st.expander("🆕 Add New Bakery"):
        n_name = st.text_input("Name")
        n_addr = st.text_input("Address")
        if st.button("Add to Map"):
            loc = Nominatim(user_agent="bollequest").geocode(n_addr)
            if loc:
                get_worksheet().append_row([n_name, "Wishlist", "", n_addr, loc.latitude, loc.longitude, "", "Other", "User", 0.1, 0, 50, get_now_dk()], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# Filter Logic
filtered = df_clean.copy()
if search_q:
    filtered = filtered[filtered.apply(lambda row: search_q.lower() in row.astype(str).str.lower().values, axis=1)]

# --- 4. ACTION CENTER (Popover) ---
st.title("🥯 BolleQuest")

if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_data = df_clean[df_clean['Bakery Name'] == name]
    row = b_data.iloc[0]
    
    with st.popover(f"📍 {name}", use_container_width=True):
        # Stock Metrics
        stock = int(b_data['Stock'].max())
        l_upd = row.get('Last Updated', '--:--')
        
        c1, c2 = st.columns(2)
        if stock <= 0:
            c1.error("SOLD OUT")
        else:
            c1.success(f"{stock} In Stock")
        c2.caption(f"Last update: {l_upd}")
        
        st.link_button("🚗 Directions", f"https://www.google.com/maps/dir/?api=1&destination={row['lat']},{row['lon']}", use_container_width=True)
        
        # Crowdsource Button
        if st.button("🚨 Report SOLD OUT", use_container_width=True):
            ws = get_worksheet()
            cell = ws.find(name)
            ws.update_cell(cell.row, 12, 0) # Stock
            ws.update_cell(cell.row, 13, get_now_dk()) # Timestamp
            st.toast("Community updated!")
            st.cache_data.clear(); time.sleep(1); st.rerun()

        st.divider()
        st.write("**Add Photo/Rating**")
        flav_name = st.text_input("Flavor Name", placeholder="e.g. Pistachio")
        rate_val = st.slider("Rating", 1.0, 5.0, 4.0, 0.5)
        price_val = st.number_input("Price (DKK)", 0, 150, 45)
        img_file = st.file_uploader("Upload Photo", type=['jpg','png'])
        
        if st.button("Submit Check-in ✅", use_container_width=True, type="primary"):
            p_url = ""
            if img_file:
                res = cloudinary.uploader.upload(img_file)
                p_url = res.get("secure_url")
            get_worksheet().append_row([name, flav_name, p_url, row['Address'], row['lat'], row['lon'], "", "Other", "User", rate_val, price_val, stock, get_now_dk()], value_input_option='USER_ENTERED')
            st.balloons(); st.cache_data.clear(); time.sleep(1); st.rerun()

# --- 5. THE TABS ---
t_map, t_list, t_gallery, t_route, t_leader, t_install = st.tabs(["📍 Map", "📜 Buns", "📸 Gallery", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for b_name in filtered['Bakery Name'].unique():
        data = filtered[filtered['Bakery Name'] == b_name]
        r = data.iloc[0]
        color = "red" if data['Stock'].max() <= 0 else "darkblue" if b_name == st.session_state.selected_bakery else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=b_name, icon=folium.Icon(color=color, icon="shopping-basket", prefix="fa")).add_to(m)
    
    map_res = st_folium(m, width="100%", height=400, key="main_map")
    if map_res and map_res.get("last_object_clicked_tooltip"):
        st.session_state.selected_bakery = map_res["last_object_clicked_tooltip"]
        st.rerun()

with t_list:
    st.subheader("Untappd-Style Feed")
    buns = filtered[filtered['Rating'] > 0].sort_values('Rating', ascending=False)
    for i, (idx, r) in enumerate(buns.iterrows()):
        # Unique key=f"btn_{i}" prevents the Duplicate ID error
        if st.button(f"⭐ {r['Rating']} | {r['Fastelavnsbolle Type']} @ {r['Bakery Name']}", key=f"btn_{i}", use_container_width=True):
            st.session_state.selected_bakery = r['Bakery Name']
            st.rerun()

with t_gallery:
    photos = filtered[filtered['Photo URL'].str.contains("http", na=False)]
    if not photos.empty:
        cols = st.columns(2)
        for i, r in enumerate(photos.tail(20).iloc[::-1].itertuples()):
            with cols[i % 2]:
                st.image(r._3, use_container_width=True)
                st.caption(f"{r._2} @ {r._1}")

with t_route:
    st.subheader("🚲 Efficient Bun Route")
    in_stock = filtered[filtered['Stock'] > 0]
    if not in_stock.empty:
        base = (55.6761, 12.5683)
        in_stock = in_stock.copy()
        in_stock['dist'] = in_stock.apply(lambda r: geodesic(base, (r['lat'], r['lon'])).km, axis=1)
        route = in_stock.sort_values('dist').head(5)
        for i, r in enumerate(route.itertuples()):
            if st.button(f"{i+1}. {r._1} ({r.dist:.1f}km)", key=f"route_{i}", use_container_width=True):
                st.session_state.selected_bakery = r._1; st.rerun()
    else:
        st.warning("No buns in stock nearby!")

with t_leader:
    st.subheader("🏆 Leaderboard")
    if 'User' in df.columns:
        leaderboard = df[df['Rating'] > 0.1]['User'].value_counts().reset_index()
        leaderboard.columns = ['User', 'Total Ratings']
        st.dataframe(leaderboard.head(10), use_container_width=True, hide_index=True)

with t_install:
    st.subheader("📲 Install on Home Screen")
    st.markdown("""
    **iOS (Safari):** Tap 'Share' > 'Add to Home Screen'
    **Android (Chrome):** Tap ⋮ > 'Install App'
    """)
