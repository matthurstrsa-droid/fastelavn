import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v11")

@st.cache_data(ttl=1)
def get_bakery_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df, worksheet

df, worksheet = get_bakery_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 2. CALCULATE STATUS MAP ---
# Group by bakery to find the HIGHEST rating they've ever received
# This ensures that if you have multiple rows, 'Tried' wins over 'Wishlist'
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. THE "CAPTURE" SECTION (Must be before Sidebar) ---
if "bakery_selector" not in st.session_state:
    st.session_state.bakery_selector = None

# --- 4. SIDEBAR: THE COMMAND CENTER ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    is_new = st.checkbox("New Bakery?", key="new_bakery_nav")
    
    if is_new:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address")
        hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Other"])
    else:
        options = sorted(df_clean['Bakery Name'].unique().tolist())
        
        # Check if the session state has a value from a map click
        target = st.session_state.bakery_selector
        default_idx = options.index(target) if target in options else 0
        
        # We use a KEY for the selectbox to ensure it syncs with session state
        bakery_name = st.selectbox("Which bakery?", options, index=default_idx, key="bakery_dropdown_widget")
        
        # Pull details for THIS specific bakery
        b_rows = df_clean[df_clean['Bakery Name'] == bakery_name]
        existing_flavs = sorted([f for f in b_rows['Fastelavnsbolle Type'].unique() if f])
        
        flavor_sel = st.selectbox("Flavour?", existing_flavs + ["➕ Add new..."], key=f"flav_sync_{bakery_name}")
        flavor_name = st.text_input("New flavor:") if flavor_sel == "➕ Add new..." else flavor_sel
        
        b_data = b_rows.iloc[0]
        f_lat, f_lon = b_data['lat'], b_data['lon']
        f_addr, f_hood = b_data.get('Address', ''), b_data.get('Neighborhood', '')

    score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # Check current status for the Wishlist checkbox
    current_best = bakery_status.get(bakery_name, 0)
    is_wish = (0.01 < current_best < 0.2) # Catch the 0.1 wishlist value
    
    wish_check = st.checkbox("Add to Wishlist? ❤️", value=is_wish, key=f"wish_sync_{bakery_name}")

    if st.button("Submit"):
        if is_new:
            loc = geolocator.geocode(address)
            f_lat, f_lon = (loc.latitude, loc.longitude) if loc else (55.67, 12.56)
            f_addr, f_hood = address, hood
        
        submit_val = 0.1 if wish_check else score
        worksheet.append_row([bakery_name, flavor_name, "", f_addr, f_lat, f_lon, "", f_hood, "User", submit_val, ""])
        
        st.cache_data.clear()
        st.session_state.bakery_selector = None # Reset
        st.rerun()

# --- 5. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map View", "📝 Checklist", "🏆 Rankings"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    for name, rating in bakery_status.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        
        # Robust Icon Selection
        if rating >= 1.0: # Actually rated
            color, icon = "green", "cutlery"
        elif 0.01 < rating < 0.2: # Wishlisted (0.1)
            color, icon = "red", "heart"
        else: # To Visit (0.0)
            color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[coords['lat'], coords['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    # Render map and catch click
    map_output = st_folium(m, width=1000, height=500, key="bakery_map_v11")
    
    # Capture click and force update
    if map_output and map_output.get("last_object_clicked_tooltip"):
        clicked = map_output["last_object_clicked_tooltip"]
        if st.session_state.bakery_selector != clicked:
            st.session_state.bakery_selector = clicked
            st.rerun()

# (Checklist and Ranking tabs follow same logic as previous version)
