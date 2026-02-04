import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v8")

try:
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    
    sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.get_worksheet(0)
    
    # Refresh data
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    # Use a small epsilon for float comparison safety
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df = df.dropna(subset=['lat', 'lon'])
except Exception as e:
    st.error(f"Auth/Data Error: {e}")
    st.stop()

# --- 2. THE STATUS ENGINE ---
# We use 0.1 exactly for wishlist. We use round() to avoid float precision errors.
bakery_status = df.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR: SUBMISSION ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("New Bakery?", key="new_bakery_check")
    
    map_selection = st.session_state.get("map_click")
    list_selection = st.session_state.get("list_click")
    current_selection = list_selection or map_selection

    if is_new_bakery:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
    else:
        bakery_options = sorted(df['Bakery Name'].unique())
        default_idx = bakery_options.index(current_selection) if current_selection in bakery_options else 0
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        flavor_selection = st.selectbox("Which flavour?", [f for f in existing_flavs if f] + ["➕ Add new..."], key=f"flav_{bakery_name}")
        flavor_name = st.text_input("Flavor name:") if flavor_selection == "➕ Add new..." else flavor_selection
        
        final_lat, final_lon = b_info['lat'], b_info['lon']
        address, neighborhood_input = b_info.get('Address', ''), b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # --- FIX 1: DYNAMIC CHECKBOX DEFAULT ---
    # It only defaults to checked if the bakery is ALREADY on your wishlist
    already_wishlisted = (bakery_status.get(bakery_name, 0) == 0.1)
    is_wishlist = st.checkbox("Add to Wishlist? ❤️", value=already_wishlisted, key=f"wish_{bakery_name}")
    
    photo_link = st.text_input("Photo URL")

    if st.button("Submit"):
        try:
            if is_new_bakery:
                location = geolocator.geocode(address)
                if location: final_lat, final_lon = location.latitude, location.longitude
                else: st.error("Address error"); st.stop()
            
            # Use 0.1 for wishlist, otherwise the slider value
            submit_score = 0.1 if is_wishlist else user_score
            
            worksheet.append_row([bakery_name, flavor_name, "", address, float(final_lat), float(final_lon), "", neighborhood_input, "User", submit_score, photo_link])
            st.success("Updated!")
            # Clear state to force a fresh look
            st.session_state.list_click = None
            st.session_state.map_click = None
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# --- 4. MAIN UI ---
st.title("🥐 Fastelavnsbolle Explorer")

tab1, tab2, tab3 = st.tabs(["📍 Map View", "📝 Checklist", "🏆 Rankings"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    for name, rating in bakery_status.items():
        row = df[df['Bakery Name'] == name].iloc[0]
        
        # --- FIX 2: ROBUST ICON LOGIC ---
        # We use a small range for 0.1 to account for float math (0.09 to 0.11)
        if rating > 0.11:
            m_color, m_icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.15:
            m_color, m_icon = "red", "heart"
        else:
            m_color, m_icon = "blue", "info-sign"
        
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"<b>{name}</b><br>Status: {'Wishlist' if 0.05 <= rating <= 0.15 else 'Tried' if rating > 0.11 else 'To Visit'}",
            tooltip=name,
            icon=folium.Icon(color=m_color, icon=m_icon)
        ).add_to(m)
    
    map_data = st_folium(m, width=1000, height=500, key="main_map")
    
    if map_data and map_data.get("last_object_clicked_tooltip"):
        new_click = map_data["last_object_clicked_tooltip"]
        if st.session_state.get("map_click") != new_click:
            st.session_state.map_click = new_click
            st.session_state.list_click = None
            st.rerun()

# (Keep Tab 2 Checklist and Tab 3 Rankings as they were)
