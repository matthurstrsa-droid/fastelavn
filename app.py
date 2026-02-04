import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v12")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_data(ttl=2)
def load_data():
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    df = pd.DataFrame(worksheet.get_all_records())
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df, worksheet

df, worksheet = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 2. SIDEBAR (Add, Rate, Remove) ---
with st.sidebar:
    st.header("🥯 Bakery Actions")
    
    is_new = st.checkbox("➕ Add New Bakery to Database", key="new_bakery_toggle")
    
    if is_new:
        st.subheader("New Bakery Details")
        new_name = st.text_input("Bakery Name")
        new_flav = st.text_input("Flavor Name")
        new_addr = st.text_input("Address (Copenhagen)")
        new_hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
        
        if st.button("Add to Map"):
            loc = geolocator.geocode(new_addr)
            if loc:
                # Add with 0.0 rating as a "To Visit" pin
                worksheet.append_row([new_name, new_flav, "", new_addr, loc.latitude, loc.longitude, "", new_hood, "User", 0.0, ""])
                st.success(f"{new_name} added!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Could not find that address.")

    else:
        # --- EXISTING BAKERY LOGIC ---
        options = sorted(df_clean['Bakery Name'].unique().tolist())
        current_idx = options.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in options else 0
        
        chosen_bakery = st.selectbox("Select Bakery", options, index=current_idx)
        st.session_state.selected_bakery = chosen_bakery

        b_rows = df_clean[df_clean['Bakery Name'] == chosen_bakery]
        current_max_rating = bakery_status.get(chosen_bakery, 0)
        is_wishlisted = (0.05 <= current_max_rating <= 0.2)

        # OPTION A: Remove from Wishlist (Only shows if it IS wishlisted)
        if is_wishlisted:
            st.info("❤️ This is on your wishlist!")
            if st.button("❌ Remove from Wishlist"):
                # Logic: Find the row where Rating is 0.1 and delete it
                cell = worksheet.find(chosen_bakery)
                # Note: This is a simple delete. In a large DB, we'd target the specific row index.
                rows = worksheet.get_all_values()
                for i, row in enumerate(rows):
                    if row[0] == chosen_bakery and (0.05 <= float(row[9] or 0) <= 0.2):
                        worksheet.delete_rows(i + 1)
                        break
                st.warning(f"Removed {chosen_bakery}")
                st.cache_data.clear()
                st.rerun()

        # OPTION B: Rate or Wishlist
        st.divider()
        flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f])
        f_sel = st.selectbox("Flavor", flavs + ["➕ New..."], key=f"f_{chosen_bakery}")
        f_name = st.text_input("New flavor name:") if f_sel == "➕ New..." else f_sel
        
        mode = st.radio("Action:", ["Rate it", "Add to Wishlist"], index=1 if is_wishlisted else 0, key=f"m_{chosen_bakery}")
        
        if mode == "Rate it":
            score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
            if st.button("Submit Rating ✅"):
                b_data = b_rows.iloc[0]
                worksheet.append_row([chosen_bakery, f_name, "", b_data['Address'], b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], "User", score, ""])
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("Confirm Wishlist ❤️"):
                b_data = b_rows.iloc[0]
                worksheet.append_row([chosen_bakery, f_name, "", b_data['Address'], b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], "User", 0.1, ""])
                st.cache_data.clear(); st.rerun()

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2 = st.tabs(["📍 Map View", "📝 Checklist"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        row = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(location=[row['lat'], row['lon']], tooltip=name,
                       icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    map_data = st_folium(m, width=1100, height=500, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Interactive Checklist")
    # Table logic as before...
    items = [{"Status": ("✅ Tried" if bakery_status.get(n,0) >= 1.0 else "❤️ Wishlist" if 0.05 <= bakery_status.get(n,0) <= 0.2 else "⭕ To Visit"), "Bakery": n} for n in sorted(df_clean['Bakery Name'].unique())]
    st.data_editor(pd.DataFrame(items), hide_index=True, use_container_width=True)
