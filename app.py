import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim  # The "Address Lookup" tool

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer") # Initialize Geocoder

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

# --- 2. SIDEBAR: SUBMIT RATING OR NEW BAKERY ---
with st.sidebar:
    st.header("⭐ Rate or Add a Bakery")
    
    is_new_bakery = st.checkbox("Bakery not on the map? Add it!")
    
    if is_new_bakery:
        bakery_name = st.text_input("New Bakery Name")
        flavor_name = st.text_input("What flavor did you try?")
        # Replaced lat/lon input with Address
        address = st.text_input("Address (e.g., Gammel Kongevej 109, Copenhagen)")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Christianshavn", "Amager", "Frederiksberg", "Other"])
        
        # Internal placeholders for geocoding
        submit_lat, submit_lon = None, None
    else:
        bakery_name = st.selectbox("Which bakery?", sorted(df['Bakery Name'].unique()))
        
        existing_flavs = df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist()
        flavor_selection = st.selectbox("Which flavour?", existing_flavs + ["➕ Add new flavour..."])
        
        if flavor_selection == "➕ Add new flavour...":
            flavor_name = st.text_input("Type the new flavour name:")
        else:
            flavor_name = flavor_selection
            
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        submit_lat, submit_lon, address = b_info['lat'], b_info['lon'], b_info.get('Address', '')
        neighborhood_input = b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 5.0, 3.0, step=0.25)
    photo_link = st.text_input("Photo Link (Optional)")

    if st.button("Submit to Google Sheets"):
        try:
            # If it's a new bakery, we need to find the lat/lon FROM the address
            if is_new_bakery:
                with st.spinner("Finding bakery on the map..."):
                    location = geolocator.geocode(address)
                    if location:
                        submit_lat = location.latitude
                        submit_lon = location.longitude
                    else:
                        st.error("Could not find that address. Try adding ', Copenhagen' at the end.")
                        st.stop()

            new_row = [
                bakery_name, flavor_name, "", address, 
                float(submit_lat), float(submit_lon), "", neighborhood_input, 
                "App User", user_score, photo_link
            ]
            worksheet.append_row(new_row)
            st.success(f"Saved {flavor_name} from {bakery_name}!")
            st.balloons()
            st.rerun()
        except Exception as e:
            st.error(f"Error saving data: {e}")

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Fastelavnsbolle Tracker")

all_neighborhoods = ["All"] + sorted([n for n in df['Neighborhood'].unique() if n])
selected_n = st.selectbox("📍 Filter by Neighborhood", all_neighborhoods)

display_df = df if selected_n == "All" else df[df['Neighborhood'] == selected_n]

tab1, tab2 = st.tabs(["📍 Map", "🏆 Rankings"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    for _, row in display_df.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"<b>{row['Bakery Name']}</b><br>{row['Fastelavnsbolle Type']}<br>Rating: {row['Rating']}/10",
            tooltip=row['Bakery Name']
        ).add_to(m)
    st_folium(m, width=900, height=500, key="main_map")

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top Bakeries")
        b_stats = display_df.groupby('Bakery Name')['Rating'].agg(['mean', 'count']).reset_index()
        b_stats.columns = ['Bakery Name', 'Avg Rating', 'Reviews']
        st.dataframe(b_stats.sort_values('Avg Rating', ascending=False), hide_index=True, use_container_width=True)
    with col2:
        st.subheader("Top Flavours")
        f_stats = display_df.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].agg(['mean', 'count']).reset_index()
        f_stats.columns = ['Flavour', 'Bakery', 'Avg Rating', 'Reviews']
        st.dataframe(f_stats.sort_values('Avg Rating', ascending=False), hide_index=True, use_container_width=True)

