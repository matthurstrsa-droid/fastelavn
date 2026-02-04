import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v3")

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

# --- 2. THE MAP (Moved up so we can capture clicks) ---
st.title("🥐 Copenhagen Fastelavnsbolle 2026")

all_neighborhoods = ["All"] + sorted([n for n in df['Neighborhood'].unique() if n])
selected_n = st.selectbox("📍 Filter by Neighborhood", all_neighborhoods)
display_df = df if selected_n == "All" else df[df['Neighborhood'] == selected_n]

tab1, tab2 = st.tabs(["📍 Map View", "🏆 Leaderboards"])

# We initialize a variable to hold the clicked bakery name
clicked_bakery = None

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    for _, row in display_df.iterrows():
        photo_val = row.get('PhotoURL', '')
        img_tag = f'<img src="{photo_val}" width="180px" style="border-radius:8px; margin-top:5px;">' if photo_val else ""
        
        popup_content = f"""
        <div style="font-family: Arial; min-width: 150px;">
            <b>{row['Bakery Name']}</b><br>
            {row['Fastelavnsbolle Type']}<br>
            Score: {row['Rating']}/10<br>
            {img_tag}
            <p style='color:blue;'>Click marker to select for rating!</p>
        </div>
        """
        
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=folium.Popup(popup_content, max_width=200),
            tooltip=row['Bakery Name']
        ).add_to(m)
    
    # --- CAPTURE CLICK DATA ---
    map_data = st_folium(m, width=1000, height=500, key="main_map")
    
    # If a user clicks a marker, get the name from the tooltip
    if map_data.get("last_object_clicked_tooltip"):
        clicked_bakery = map_data["last_object_clicked_tooltip"]
        st.info(f"Selected: **{clicked_bakery}**. Use the sidebar to add your rating!")

# --- 3. SIDEBAR: SUBMIT RATING ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("Bakery not on the map?")
    
    if is_new_bakery:
        bakery_name = st.text_input("New Bakery Name")
        flavor_name = st.text_input("What flavor?")
        address = st.text_input("Address")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Other"])
    else:
        # 1. Sync Bakery with Map Click
        bakery_options = sorted(df['Bakery Name'].unique())
        default_idx = 0
        if clicked_bakery in bakery_options:
            default_idx = bakery_options.index(clicked_bakery)
            
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        # 2. Get flavors for THIS bakery
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        existing_flavs = [f for f in existing_flavs if f] # Remove blanks
        
        # 3. Add the "Add New" option
        flavor_options = existing_flavs + ["➕ Add new flavour..."]
        
        # --- THE FIX ---
        # We add a unique key based on the bakery name. 
        # When bakery_name changes, this widget 'resets'.
        flavor_selection = st.selectbox(
            "Which flavour?", 
            flavor_options, 
            key=f"flavor_sel_{bakery_name}" 
        )
        
        if flavor_selection == "➕ Add new flavour...":
            flavor_name = st.text_input("Type the new flavour name:", key=f"new_flavor_{bakery_name}")
        else:
            flavor_name = flavor_selection

# --- 4. RANKINGS (Tab 2) ---
with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top Bakeries")
        st.dataframe(display_df.groupby('Bakery Name')['Rating'].agg(['mean', 'count']).reset_index().sort_values('mean', ascending=False), hide_index=True)
    with col2:
        st.subheader("Top Flavours")
        st.dataframe(display_df.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].agg(['mean', 'count']).reset_index().sort_values('mean', ascending=False), hide_index=True)
        


