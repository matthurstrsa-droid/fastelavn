import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- PAGE SETUP ---
st.set_page_config(page_title="Fastelavnsbolle Guide 2026", layout="wide")
st.title("🥐 Your 2026 Fastelavnsbolle Guide")

# --- 1. CONNECT TO YOUR GOOGLE SHEET ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Replace the URL below with your 'fastelavnsbolle_guide_2025' share link
url = "https://docs.google.com/spreadsheets/d/1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo/edit?usp=sharing"
df = conn.read(spreadsheet=url)

# --- 2. GEOCODING FUNCTION ---
# This converts your 'Address' column into map coordinates
geolocator = Nominatim(user_agent="fastelavn_app")

@st.cache_data
def get_coords(address):
    try:
        location = geolocator.geocode(address + ", Copenhagen")
        return (location.latitude, location.longitude) if location else (None, None)
    except:
        return (None, None)

# --- 3. MAIN APP INTERFACE ---
st.subheader("📍 Bakery Locations & Details")

# Create the Map
m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)

# Add markers based on your Spreadsheet data
for index, row in df.iterrows():
    lat, lon = get_coords(row['Address'])
    if lat:
        popup_text = f"<b>{row['Bakery Name']}</b><br>{row['Fastelavnsbolle Type']}<br>Price: {row['Price (DKK)']} DKK"
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=row['Bakery Name']
        ).add_to(m)

st_folium(m, width="100%", height=500)

# --- 4. DATA EXPLORER ---
st.subheader("📊 Full Bun Inventory")
st.dataframe(df[['Bakery Name', 'Fastelavnsbolle Type', 'Price (DKK)', 'Neighborhood']], use_container_width=True)


