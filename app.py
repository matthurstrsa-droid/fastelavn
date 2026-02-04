import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# Initialize Session State early
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
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    return df, worksheet

df, worksheet = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# Helper for icon logic
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 2. THE UI TABS (The "Inputs") ---
st.title("🥐 Copenhagen Bakery Explorer")
tab1, tab2 = st.tabs(["📍 Map View", "📝 Checklist"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        row = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        
        # Icon Logic: 0.1 = Wishlist (Red), >0.1 = Tried (Green)
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[row['lat'], row['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    # Render map
    map_data = st_folium(m, width=1100, height=500, key="map")
    
    # Catch Map Click
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with tab2:
    # Build a simple dataframe for the list
    list_items = []
    for name in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(name, 0)
        stat = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.05 <= r <= 0.2 else "⭕ To Visit"
        list_items.append({"Status": stat, "Bakery": name})
    
    # Show as a selectable list
    selected_row = st.selectbox("Search/Pick from list:", ["-- None --"] + [i["Bakery"] for i in list_items])
    if selected_row != "-- None --" and st.session_state.selected_bakery != selected_row:
        st.session_state.selected_bakery = selected_row
        st.rerun()

# --- 3. THE SIDEBAR (The "Responder") ---
with st.sidebar:
    st.header("⭐ Rate or Wishlist")
    
    options = sorted(df_clean['Bakery Name'].unique().tolist())
    
    # Sync: Use the session state to set the index
    current_bakery = st.session_state.selected_bakery
    idx = options.index(current_bakery) if current_bakery in options else 0
    
    # Use a specific KEY for the selectbox to lock it to session state
    chosen_bakery = st.selectbox("Selected Bakery", options, index=idx, key="sidebar_bakery_choice")
    
    # Update session state if the user manually changes the sidebar dropdown
    if chosen_bakery != st.session_state.selected_bakery:
        st.session_state.selected_bakery = chosen_bakery

    # --- FLAVOR LOGIC ---
    b_rows = df_clean[df_clean['Bakery Name'] == chosen_bakery]
    existing_flavs = sorted([f for f in b_rows['Fastelavnsbolle Type'].unique() if f])
    
    f_sel = st.selectbox("Flavour", existing_flavs + ["➕ New..."], key=f"f_{chosen_bakery}")
    f_name = st.text_input("Type flavor:") if f_sel == "➕ New..." else f_sel

    # --- RATING & WISHLIST ---
    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # Reset wishlist checkbox based on the currently selected bakery
    is_wished = (0.05 <= bakery_status.get(chosen_bakery, 0) <= 0.2)
    wish_check = st.checkbox("Add to Wishlist? ❤️", value=is_wished, key=f"w_{chosen_bakery}")

    if st.button("Submit"):
        b_data = b_rows.iloc[0]
        final_score = 0.1 if wish_check else user_score
        
        worksheet.append_row([
            chosen_bakery, f_name, "", b_data['Address'], 
            b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], 
            "User", final_score, ""
        ])
        
        st.success(f"Updated {chosen_bakery}!")
        st.cache_data.clear()
        st.rerun()
