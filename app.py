import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v9")

@st.cache_data(ttl=5) # Cache data for 5 seconds to prevent constant hitting of GS
def get_bakery_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    return df, worksheet

try:
    df, worksheet = get_bakery_data()
    df = df.dropna(subset=['lat', 'lon'])
except Exception as e:
    st.error(f"Data Connection Error: {e}")
    st.stop()

# --- 2. CALCULATE STATUS ---
# Get the highest rating per bakery to determine icon color
status_map = df.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR: RATE & ADD ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    # Handle Selection
    map_click = st.session_state.get("last_clicked")
    list_click = st.session_state.get("selected_from_list")
    current_bakery = list_click or map_click

    is_new = st.checkbox("New Bakery?", key="new_bakery_toggle")
    
    if is_new:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address")
        hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Other"])
    else:
        options = sorted(df['Bakery Name'].unique().tolist())
        idx = options.index(current_bakery) if current_bakery in options else 0
        bakery_name = st.selectbox("Which bakery?", options, index=idx)
        
        # Auto-fill known data
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        flavor_name = st.text_input("Flavor Name (e.g. Gammeldags)")
        address = b_info.get('Address', '')
        hood = b_info.get('Neighborhood', '')

    score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # Check if this bakery is already wishlisted
    is_already_wish = 0.05 <= status_map.get(bakery_name, 0) <= 0.15
    wish_check = st.checkbox("Add to Wishlist? ❤️", value=is_already_wish, key=f"wish_check_{bakery_name}")

    if st.button("Submit to Sheet"):
        if is_new:
            loc = geolocator.geocode(address)
            lat, lon = (loc.latitude, loc.longitude) if loc else (55.67, 12.56)
        else:
            lat, lon = b_info['lat'], b_info['lon']

        final_score = 0.1 if wish_check else score
        worksheet.append_row([bakery_name, flavor_name, "", address, lat, lon, "", hood, "User", final_score, ""])
        
        # Reset and Rerun
        st.session_state.last_clicked = None
        st.session_state.selected_from_list = None
        st.cache_data.clear()
        st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Tracker")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Rankings"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in status_map.items():
        coords = df[df['Bakery Name'] == name].iloc[0]
        
        # ICON LOGIC
        if rating > 0.15: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.15: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[coords['lat'], coords['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    map_res = st_folium(m, width=1000, height=500, key="bakery_map")
    
    if map_res and map_res.get("last_object_clicked_tooltip"):
        clicked = map_res["last_object_clicked_tooltip"]
        if st.session_state.get("last_clicked") != clicked:
            st.session_state.last_clicked = clicked
            st.session_state.selected_from_list = None
            st.rerun()

with t2:
    st.subheader("Your Bakery Progress")
    # Build Display List
    check_list = []
    for name in sorted(df['Bakery Name'].unique()):
        r = status_map.get(name, 0)
        stat = "✅ Tried" if r > 0.15 else "❤️ Wishlist" if 0.05 <= r <= 0.15 else "⭕ To Visit"
        check_list.append({"Status": stat, "Bakery": name})
    
    check_df = pd.DataFrame(check_list)
    
    # Interactive Table
    ed_df = st.data_editor(
        check_df,
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])},
        disabled=["Bakery"], hide_index=True, use_container_width=True, key="list_editor"
    )

    # Change Detection
    for i, row in ed_df.iterrows():
        if row['Status'] != check_list[i]['Status']:
            if row['Status'] == "✅ Tried":
                st.session_state.selected_from_list = row['Bakery']
                st.rerun()
            elif row['Status'] == "❤️ Wishlist":
                b = df[df['Bakery Name'] == row['Bakery']].iloc[0]
                worksheet.append_row([row['Bakery'], "Wishlist", "", b['Address'], b['lat'], b['lon'], "", b['Neighborhood'], "User", 0.1, ""])
                st.cache_data.clear()
                st.rerun()

with t3:
    st.subheader("Top Rated")
    real_ratings = df[df['Rating'] > 0.15]
    if not real_ratings.empty:
        st.dataframe(real_ratings.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False))
