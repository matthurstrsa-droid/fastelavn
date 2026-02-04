import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# Initialize Session State
if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_data(ttl=2)
def load_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    
    # Ensure columns exist and are numeric
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df, worksheet

df, worksheet = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# Status Helper
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 2. TABS (The Trigger) ---
st.title("🥐 Copenhagen Bakery Explorer")
tab1, tab2 = st.tabs(["📍 Map View", "📝 Checklist"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        # Get coordinates for this specific bakery name
        b_geo = df_clean[df_clean['Bakery Name'] == name]
        if not b_geo.empty:
            row = b_geo.iloc[0]
            # Color logic
            if rating >= 1.0: color, icon = "green", "cutlery"
            elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
            else: color, icon = "blue", "info-sign"
                
            folium.Marker(
                location=[row['lat'], row['lon']],
                tooltip=name,
                icon=folium.Icon(color=color, icon=icon)
            ).add_to(m)
    
    map_data = st_folium(m, width=1100, height=500, key="map")
    
    # Sync Map Click to Sidebar
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with tab2:
    # Build a simple search/pick list
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    list_choice = st.selectbox("Search/Pick from list:", ["-- Select --"] + all_names)
    if list_choice != "-- Select --" and st.session_state.selected_bakery != list_choice:
        st.session_state.selected_bakery = list_choice
        st.rerun()

# --- 3. SIDEBAR (The Form) ---
with st.sidebar:
    st.header("⭐ Rate or Wishlist")
    
    # Defensive check: ensure our options list isn't empty
    options = sorted(df_clean['Bakery Name'].unique().tolist())
    
    if not options:
        st.warning("No bakery data found.")
        st.stop()

    # Determine default index based on session state
    current_sel = st.session_state.selected_bakery
    idx = options.index(current_sel) if current_sel in options else 0
    
    # The Dropdown
    bakery_name = st.selectbox("Bakery", options, index=idx, key="sidebar_choice")
    
    # --- FLAVOR LOGIC (Defensive) ---
    b_rows = df_clean[df_clean['Bakery Name'] == bakery_name]
    
    if not b_rows.empty:
        # Only try to sort if the column exists and has values
        col = 'Fastelavnsbolle Type'
        existing_flavs = sorted([str(f) for f in b_rows[col].unique() if f and str(f).strip()])
        
        f_sel = st.selectbox("Flavour", existing_flavs + ["➕ New..."], key=f"f_{bakery_name}")
        f_name = st.text_input("Type flavor:") if f_sel == "➕ New..." else f_sel
        
        # --- RATING & WISHLIST ---
        score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        
        # Check if already wishlisted
        is_wished = (0.05 <= bakery_status.get(bakery_name, 0) <= 0.2)
        wish_check = st.checkbox("Add to Wishlist? ❤️", value=is_wished, key=f"w_{bakery_name}")

        if st.button("Submit"):
            b_data = b_rows.iloc[0]
            final_score = 0.1 if wish_check else score
            
            worksheet.append_row([
                bakery_name, f_name, "", b_data.get('Address', ''), 
                b_data['lat'], b_data['lon'], "", b_data.get('Neighborhood', ''), 
                "User", final_score, ""
            ])
            
            st.success(f"Updated {bakery_name}!")
            st.cache_data.clear()
            st.session_state.selected_bakery = bakery_name
            st.rerun()
    else:
        st.error("Could not find data for the selected bakery.")
