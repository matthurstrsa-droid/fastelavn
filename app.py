import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

# 1. Page Config
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")

st.title("🥐 The Great 2026 Fastelavnsbolle Map")

# 2. The Data (This replaces the need for Google Sheets for now)
if 'db' not in st.session_state:
    st.session_state.db = pd.DataFrame([
        {"Bakery": "Juno the Bakery", "City": "Copenhagen", "Flavor": "Pistachio", "Rating": 9.5, "lat": 55.7039, "lon": 12.5830},
        {"Bakery": "Hart Bageri", "City": "Copenhagen", "Flavor": "Classic Custard", "Rating": 8.8, "lat": 55.6791, "lon": 12.5400},
        {"Bakery": "Andersen Bakery", "City": "Copenhagen", "Flavor": "Yuzu Raspberry", "Rating": 9.2, "lat": 55.6672, "lon": 12.5765},
    ])

# 3. Sidebar to add new buns (stores them while the app is open)
with st.sidebar:
    st.header("Rate a Bun")
    with st.form("add_form", clear_on_submit=True):
        name = st.text_input("Bakery Name")
        flavor = st.text_input("Flavor")
        score = st.slider("Rating", 1.0, 10.0, 8.0)
        st.write("Tip: Use 55.67 for Lat and 12.56 for Lon for Copenhagen center.")
        lat = st.number_input("Latitude", value=55.6761, format="%.4f")
        lon = st.number_input("Longitude", value=12.5683, format="%.4f")
        submit = st.form_submit_button("Add to Map")
        
        if submit and name:
            new_entry = pd.DataFrame([{"Bakery": name, "City": "Copenhagen", "Flavor": flavor, "Rating": score, "lat": lat, "lon": lon}])
            st.session_state.db = pd.concat([st.session_state.db, new_entry], ignore_index=True)
            st.success("Added! Note: This is a demo; data won't save permanently yet.")

# 4. Display Map and Leaderboard
col_left, col_right = st.columns([2, 1])

with col_left:
    m = folium.Map(location=[55.68, 12.58], zoom_start=12)
    for _, row in st.session_state.db.iterrows():
        folium.Marker(
            [row['lat'], row['lon']], 
            popup=f"{row['Bakery']} - {row['Rating']}/10",
            tooltip=row['Bakery']
        ).add_to(m)
    st_folium(m, width="100%", height=500)

with col_right:
    st.subheader("🏆 Leaderboard")
    st.dataframe(st.session_state.db.sort_values("Rating", ascending=False)[["Bakery", "Rating"]], hide_index=True)
