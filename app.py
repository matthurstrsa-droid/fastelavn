import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_final_v10")

@st.cache_data(ttl=2)
def get_bakery_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    # Clean data
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    return df, worksheet

df, worksheet = get_bakery_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 2. THE BRAINS: Global Status Map ---
# Finds the best status for every bakery name
status_map = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR: THE COMMAND CENTER ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    # Check for Map or Checklist interaction
    # We use a single session variable to prevent conflicts
    if "bakery_selector" not in st.session_state:
        st.session_state.bakery_selector = None

    is_new = st.checkbox("New Bakery?", key="new_bakery_nav")
    
    if is_new:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address (Copenhagen)")
        hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Other"])
    else:
        options = sorted(df_clean['Bakery Name'].unique().tolist())
        # Sync selection from Map or Checklist
        try:
            default_idx = options.index(st.session_state.bakery_selector) if st.session_state.bakery_selector in options else 0
        except:
            default_idx = 0
            
        bakery_name = st.selectbox("Which bakery?", options, index=default_idx, key="main_bakery_dropdown")
        
        # --- FLAVOR FIX ---
        # Get flavors specifically for THIS bakery
        bakery_rows = df_clean[df_clean['Bakery Name'] == bakery_name]
        existing_flavs = sorted([f for f in bakery_rows['Fastelavnsbolle Type'].unique() if f])
        
        flavor_sel = st.selectbox("Which flavour?", existing_flavs + ["➕ Add new..."], key=f"flavor_box_{bakery_name}")
        flavor_name = st.text_input("Type new flavor:") if flavor_sel == "➕ Add new..." else flavor_sel
        
        # Pull coordinates
        b_data = bakery_rows.iloc[0]
        final_lat, final_lon = b_data['lat'], b_data['lon']
        final_addr, final_hood = b_data.get('Address', ''), b_data.get('Neighborhood', '')

    score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # --- WISHLIST FIX ---
    # Check if currently wishlisted (0.05 to 0.15 range)
    current_rating = status_map.get(bakery_name, 0)
    is_wish = 0.05 <= current_rating <= 0.15
    wish_check = st.checkbox("Add to Wishlist? ❤️", value=is_wish, key=f"wish_check_{bakery_name}")

    if st.button("Submit to Google Sheets"):
        if is_new:
            loc = geolocator.geocode(address)
            final_lat, final_lon = (loc.latitude, loc.longitude) if loc else (55.67, 12.56)
            final_addr, final_hood = address, hood
        
        submit_val = 0.1 if wish_check else score
        worksheet.append_row([bakery_name, flavor_name, "", final_addr, final_lat, final_lon, "", final_hood, "User", submit_val, ""])
        
        st.success("Success!")
        st.cache_data.clear()
        st.session_state.bakery_selector = None
        st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map View", "📝 Checklist", "🏆 Rankings"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in status_map.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        
        # Icon Logic
        if rating > 0.15: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.15: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[coords['lat'], coords['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    # st_folium captures the click
    map_output = st_folium(m, width=1000, height=500, key="bakery_map_main")
    
    if map_output and map_output.get("last_object_clicked_tooltip"):
        clicked_name = map_output["last_object_clicked_tooltip"]
        if st.session_state.bakery_selector != clicked_name:
            st.session_state.bakery_selector = clicked_name
            st.rerun()

with t2:
    st.subheader("Interactive Checklist")
    # Data for the table
    table_data = []
    for name in sorted(df_clean['Bakery Name'].unique()):
        r = status_map.get(name, 0)
        stat = "✅ Tried" if r > 0.15 else "❤️ Wishlist" if 0.05 <= r <= 0.15 else "⭕ To Visit"
        table_data.append({"Status": stat, "Bakery Name": name})
    
    display_df = pd.DataFrame(table_data)
    
    edited_table = st.data_editor(
        display_df,
        column_config={"Status": st.column_config.SelectboxColumn("Quick Action", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])},
        disabled=["Bakery Name"], hide_index=True, use_container_width=True, key="checklist_editor_main"
    )

    # Detect Checklist interaction
    for i, row in edited_table.iterrows():
        if row['Status'] != display_df.iloc[i]['Status']:
            sel_name = row['Bakery Name']
            if row['Status'] == "✅ Tried":
                st.session_state.bakery_selector = sel_name
                st.rerun()
            elif row['Status'] == "❤️ Wishlist":
                b_row = df_clean[df_clean['Bakery Name'] == sel_name].iloc[0]
                worksheet.append_row([sel_name, "Wishlist", "", b_row['Address'], b_row['lat'], b_row['lon'], "", b_row['Neighborhood'], "User", 0.1, ""])
                st.cache_data.clear()
                st.rerun()

with t3:
    st.subheader("Leaderboard")
    real_data = df_clean[df_clean['Rating'] > 0.15]
    if not real_data.empty:
        st.dataframe(real_data.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False))
