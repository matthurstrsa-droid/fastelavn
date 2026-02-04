import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import folium
from streamlit_folium import st_folium

# --- APP SETUP ---
st.set_page_config(page_title="DK Fastelavnsbolle Map 2026", layout="wide")
st.title("🥐 The Great 2026 Fastelavnsbolle Map")

# --- DATABASE CONNECTION (Google Sheets) ---
# This connects to a sheet where everyone's ratings are stored
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl="0m") # Set ttl to 0 so we always see the latest buns

df = load_data()

# --- FEATURE 1: ADD A NEW RATING ---
with st.sidebar:
    st.header("Rate a New Bun")
    with st.form("add_form"):
        bakery_name = st.text_input("Bakery Name")
        city = st.selectbox("City", ["Copenhagen", "Aarhus", "Odense", "Aalborg", "Other"])
        flavor = st.text_input("Flavor")
        rating = st.slider("Rating (1-10)", 1, 10, 5)
        
        # In a real app, you'd geocode this, but for now we'll store coordinates
        # Tip: Use a hidden lookup table for major bakery coordinates!
        lat = st.number_input("Lat (e.g. 55.67)", format="%.4f", value=55.6761)
        lon = st.number_input("Lon (e.g. 12.56)", format="%.4f", value=12.5683)
        
        submit = st.form_submit_button("Submit to Community")
        
        if submit:
            new_data = pd.DataFrame([{"Bakery": bakery_name, "City": city, "Flavor": flavor, "Rating": rating, "lat": lat, "lon": lon}])
            # Append logic for Google Sheets goes here
            st.success("Rating added! (Requires GSheets Write Access)")

# --- FEATURE 2: MAP VIEW ---
st.subheader("📍 Where the Buns Are")

# Center map on Denmark
m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)

# Add markers for each bakery in the shared database
for index, row in df.iterrows():
    folium.Marker(
        [row['lat'], row['lon']],
        popup=f"{row['Bakery']}: {row['Rating']}/10",
        tooltip=row['Bakery']
    ).add_to(m)

st_folium(m, width=1000, height=500)

# --- FEATURE 3: AGGREGATED LEADERBOARD ---
st.subheader("🏆 The 2026 Leaderboard")
if not df.empty:
    leaderboard = df.groupby("Bakery")["Rating"].agg(['mean', 'count']).sort_values(by="mean", ascending=False)
    leaderboard.columns = ["Average Rating", "Number of Reviews"]
    st.dataframe(leaderboard, use_container_width=True)