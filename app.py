import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v4")

try:
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    
    sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.get_worksheet(0)
    
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
    df = df.dropna(subset=['lat', 'lon'])
except Exception as e:
    st.error(f"Auth/Data Error: {e}")
    st.stop()

# --- 2. PROGRESS LOGIC ---
# A bakery is "Tried" if it has a numeric rating
tried_bakeries = df[df['Rating'] > 0]['Bakery Name'].unique().tolist()

# --- 3. SIDEBAR: PROGRESS & SUBMISSION ---
with st.sidebar:
    st.header("📊 Your Progress")
    total_spots = len(df['Bakery Name'].unique())
    visited_spots = len(tried_bakeries)
    st.write(f"Conquered: {visited_spots} / {total_spots}")
    st.progress(visited_spots / total_spots if total_spots > 0 else 0)
    
    st.divider()
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("New Bakery?")
    
    # Capture map clicks for auto-selection
    clicked_bakery = st.session_state.get("clicked_bakery", None)

    if is_new_bakery:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address (incl. Copenhagen)")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
    else:
        bakery_options = sorted(df['Bakery Name'].unique())
        default_idx = bakery_options.index(clicked_bakery) if clicked_bakery in bakery_options else 0
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        flavor_selection = st.selectbox("Which flavour?", [f for f in existing_flavs if f] + ["➕ Add new..."], key=f"flav_{bakery_name}")
        flavor_name = st.text_input("Flavor name:") if flavor_selection == "➕ Add new..." else flavor_selection
        
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        final_lat, final_lon = b_info['lat'], b_info['lon']
        address, neighborhood_input = b_info.get('Address', ''), b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    is_wishlist = st.checkbox("Add to Wishlist? ❤️")
    photo_link = st.text_input("Photo URL")

    if st.button("Submit"):
        try:
            if is_new_bakery:
                location = geolocator.geocode(address)
                if location:
                    final_lat, final_lon = location.latitude, location.longitude
                else:
                    st.error("Address error")
                    st.stop()
            
            # Using '99' as a placeholder rating for wishlist items
            submit_score = 0.1 if is_wishlist and user_score == 8.0
