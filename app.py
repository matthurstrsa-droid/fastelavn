import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")

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
        new_lat = st.number_input("Latitude", format="%.4f", value=55.6761)
        new_lon = st.number_input("Longitude", format="%.4f", value=12.5683)
        address = st.text_input("Address")
        # Added Neighborhood input for new bakeries
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Christianshavn", "Amager", "Frederiksberg", "Other"])
    else:
        bakery_name = st.selectbox("Which bakery?", sorted(df['Bakery Name'].unique()))
        
        existing_flavs = df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist()
        flavor_selection = st.selectbox("Which flavour?", existing_flavs + ["➕ Add new flavour..."])
        
        if flavor_selection == "➕ Add new flavour...":
            flavor_name = st.text_input("Type the new flavour name:")
        else:
            flavor_name = flavor_selection
            
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        new_lat, new_lon, address = b_info['lat'], b_info['lon'], b_info.get('Address', '')
        neighborhood_input = b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    photo_link = st.text_input("Photo Link (Optional)")

    if st.button("Submit to Google Sheets"):
        try:
            new_row = [
                bakery_name, flavor_name, "", address, 
                float(new_lat), float(new_lon), "", neighborhood_input, 
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

# NEIGHBORHOOD FILTER
all_neighborhoods = ["All"] + sorted([n for n in df['Neighborhood'].unique() if n])
selected_n = st.selectbox("📍 Filter by Neighborhood", all_neighborhoods)

# Filter the dataframe for the map and rankings
if selected_n != "All":
    display_df = df[df['Neighborhood'] == selected_n]
else:
    display_df = df

tab1, tab2 = st.tabs(["📍 Map", "🏆 Rankings"])

with tab1:
    st.subheader(f"Bakery Map: {selected_n}")
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    for _, row in display_df.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"{row['Bakery Name']}: {row['Fastelavnsbolle Type']} ({row['Rating']}/10)",
            tooltip=row['Bakery Name']
        ).add_to(m)
    st_folium(m, width=900,
             )
