import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v7")

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
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df = df.dropna(subset=['lat', 'lon'])
except Exception as e:
    st.error(f"Auth/Data Error: {e}")
    st.stop()

# --- 2. THE STATUS ENGINE ---
# This creates a dictionary of the HIGHEST rating for every bakery
# 0.0 = Untouched, 0.1 = Wishlist, >0.1 = Tried
bakery_status = df.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR: SUBMISSION ---
with st.sidebar:
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("New Bakery?")
    
    # CRITICAL FIX: Determine which bakery is selected
    # Priority: Checklist Click > Map Click > Default
    map_selection = st.session_state.get("map_click")
    list_selection = st.session_state.get("list_click")
    current_selection = list_selection or map_selection

    if is_new_bakery:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
    else:
        bakery_options = sorted(df['Bakery Name'].unique())
        try:
            default_idx = bakery_options.index(current_selection) if current_selection in bakery_options else 0
        except:
            default_idx = 0
            
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        # Pull details for the selected bakery
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        flavor_selection = st.selectbox("Which flavour?", [f for f in existing_flavs if f] + ["➕ Add new..."], key=f"flav_{bakery_name}")
        flavor_name = st.text_input("Flavor name:") if flavor_selection == "➕ Add new..." else flavor_selection
        
        final_lat, final_lon = b_info['lat'], b_info['lon']
        address, neighborhood_input = b_info.get('Address', ''), b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    is_wishlist = st.checkbox("Add to Wishlist? ❤️")
    photo_link = st.text_input("Photo URL")

    if st.button("Submit"):
        try:
            if is_new_bakery:
                location = geolocator.geocode(address)
                if location: final_lat, final_lon = location.latitude, location.longitude
                else: st.error("Address error"); st.stop()
            
            submit_score = 0.1 if is_wishlist else user_score
            worksheet.append_row([bakery_name, flavor_name, "", address, float(final_lat), float(final_lon), "", neighborhood_input, "User", submit_score, photo_link])
            st.success("Updated!")
            # Reset selections on success
            st.session_state.list_click = None
            st.session_state.map_click = None
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# --- 4. MAIN UI ---
st.title("🥐 Fastelavnsbolle Explorer")

tab1, tab2, tab3 = st.tabs(["📍 Map View", "📝 Checklist", "🏆 Rankings"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    for name, rating in bakery_status.items():
        row = df[df['Bakery Name'] == name].iloc[0]
        
        # Color Logic Fix: Explicitly check for 0.1
        if rating > 0.1:
            m_color, m_icon = "green", "cutlery"
        elif rating == 0.1:
            m_color, m_icon = "red", "heart"
        else:
            m_color, m_icon = "blue", "info-sign"
        
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"{name}",
            tooltip=name,
            icon=folium.Icon(color=m_color, icon=m_icon)
        ).add_to(m)
    
    # Capture Map Data
    map_data = st_folium(m, width=1000, height=500, key="main_map")
    
    # If a user clicks a pin, update the session state and refresh
    if map_data and map_data.get("last_object_clicked_tooltip"):
        new_click = map_data["last_object_clicked_tooltip"]
        if st.session_state.get("map_click") != new_click:
            st.session_state.map_click = new_click
            st.session_state.list_click = None # Map click overrides list
            st.rerun()

with tab2:
    st.subheader("Interactive Checklist")
    # Assemble data for the checklist
    check_data = []
    for name in sorted(df['Bakery Name'].unique()):
        rating = bakery_status.get(name, 0)
        status = "✅ Tried" if rating > 0.1 else "❤️ Wishlist" if rating == 0.1 else "⭕ To Visit"
        check_data.append({"Status": status, "Bakery Name": name})
    
    check_df = pd.DataFrame(check_data)
    
    edited_df = st.data_editor(
        check_df,
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])},
        disabled=["Bakery Name"], hide_index=True, use_container_width=True, key="editor"
    )

    # Detect changes in the table
    for idx, row in edited_df.iterrows():
        if row['Status'] != check_df.iloc[idx]['Status']:
            selected_name = row['Bakery Name']
            if row['Status'] == "✅ Tried":
                st.session_state.list_click = selected_name
                st.session_state.map_click = None
                st.rerun()
            elif row['Status'] == "❤️ Wishlist":
                # Quick-add to wishlist
                b_row = df[df['Bakery Name'] == selected_name].iloc[0]
                worksheet.append_row([selected_name, "Wishlist", "", b_row['Address'], b_row['lat'], b_row['lon'], "", b_row['Neighborhood'], "User", 0.1, ""])
                st.rerun()

with tab3:
    st.subheader("Leaderboard")
    valid = df[df['Rating'] > 0.1]
    if not valid.empty:
        st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False))
