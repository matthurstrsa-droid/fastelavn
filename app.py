import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v13")

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

try:
    df, worksheet = load_data()
    df_clean = df.dropna(subset=['lat', 'lon'])
    bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# --- 2. SIDEBAR (The Control Center) ---
with st.sidebar:
    st.header("🥯 Bakery Actions")
    
    # --- ADD NEW BAKERY ---
    is_new = st.checkbox("➕ Add New Bakery to Database")
    if is_new:
        with st.form("new_bakery_form"):
            n_name = st.text_input("Bakery Name")
            n_flav = st.text_input("First Flavor")
            n_addr = st.text_input("Address (Copenhagen)")
            n_hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
            if st.form_submit_button("Add to Map"):
                loc = geolocator.geocode(n_addr)
                if loc:
                    worksheet.append_row([n_name, n_flav, "", n_addr, loc.latitude, loc.longitude, "", n_hood, "User", 0.0, ""])
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Address not found.")

    st.divider()

    # --- SELECT & RATE BAKERY ---
    options = sorted(df_clean['Bakery Name'].unique().tolist())
    idx = options.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in options else 0
    chosen_bakery = st.selectbox("Current Selection", options, index=idx)
    st.session_state.selected_bakery = chosen_bakery

    b_rows = df_clean[df_clean['Bakery Name'] == chosen_bakery]
    current_rating = bakery_status.get(chosen_bakery, 0)
    is_wish = (0.05 <= current_rating <= 0.2)

    # REMOVE BUTTON (Only if wishlisted)
    if is_wish:
        if st.button("❌ Remove from Wishlist", use_container_width=True):
            # Find row index to delete
            all_data = worksheet.get_all_values()
            for i, row in enumerate(all_data):
                if row[0] == chosen_bakery and (0.05 <= float(row[9] or 0) <= 0.2):
                    worksheet.delete_rows(i + 1)
                    break
            st.cache_data.clear()
            st.rerun()

    # FLAVOR & RATING FORM
    if not b_rows.empty:
        flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f])
        f_sel = st.selectbox("Flavor", flavs + ["➕ New..."], key=f"f_{chosen_bakery}")
        f_name = st.text_input("Flavor name:") if f_sel == "➕ New..." else f_sel
        
        mode = st.radio("Action:", ["Rate it", "Add to Wishlist"], index=1 if is_wish else 0, key=f"m_{chosen_bakery}")
        
        if st.button("Submit"):
            b_data = b_rows.iloc[0]
            val = 0.1 if mode == "Add to Wishlist" else st.slider("Rating", 1.0, 10.0, 8.0, step=0.5, key="manual_slider")
            
            # SAFE APPEND
            row_to_add = [
                str(chosen_bakery), str(f_name), "", str(b_data.get('Address', '')),
                float(b_data['lat']), float(b_data['lon']), "", 
                str(b_data.get('Neighborhood', '')), "User", float(val), ""
            ]
            worksheet.append_row(row_to_add)
            st.cache_data.clear()
            st.rerun()

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2 = st.tabs(["📍 Map View", "📝 Checklist"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[coords['lat'], coords['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        clicked = m_out["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Progress Tracker")
    # Quick Table for overview
    items = []
    for n in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.05 <= r <= 0.2 else "⭕ To Visit"
        items.append({"Status": s, "Bakery": n})
    st.table(pd.DataFrame
            )
