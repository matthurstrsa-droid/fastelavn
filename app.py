import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v14")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_data(ttl=2)
def load_data():
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Ensure numeric columns
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df, worksheet

try:
    df, worksheet = load_data()
    df_clean = df.dropna(subset=['lat', 'lon'])
    # Get the best rating for each bakery name
    bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# --- 2. SIDEBAR (The Command Center) ---
with st.sidebar:
    st.header("🥯 Bakery Actions")
    
    # ADD NEW BAKERY
    is_new = st.checkbox("➕ Add New Bakery")
    if is_new:
        with st.form("new_bakery"):
            n_name = st.text_input("Name")
            n_addr = st.text_input("Address")
            n_hood = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
            if st.form_submit_button("Add to Map"):
                loc = geolocator.geocode(n_addr)
                if loc:
                    worksheet.append_row([n_name, "Base", "", n_addr, loc.latitude, loc.longitude, "", n_hood, "User", 0.0, ""])
                    st.cache_data.clear(); st.rerun()
                else: st.error("Address not found.")
    st.divider()

    # SELECTION & ACTIONS
    all_bakeries = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_bakeries:
        target = st.session_state.selected_bakery
        idx = all_bakeries.index(target) if target in all_bakeries else 0
        chosen = st.selectbox("Current Selection", all_bakeries, index=idx)
        st.session_state.selected_bakery = chosen

        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        current_max = bakery_status.get(chosen, 0)
        is_wish = (0.01 < current_max < 0.2)

        if is_wish:
            if st.button("❌ Remove from Wishlist", use_container_width=True):
                all_rows = worksheet.get_all_values()
                for i, row in enumerate(all_rows):
                    # Column 0 is Name, Column 9 is Rating
                    if row[0] == chosen and (0.01 < float(row[9] or 0) < 0.2):
                        worksheet.delete_rows(i + 1)
                        break
                st.cache_data.clear(); st.rerun()

        st.divider()
        mode = st.radio("Action:", ["Rate it", "Add to Wishlist"], index=1 if is_wish else 0, key=f"m_{chosen}")
        
        if mode == "Rate it":
            score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
            if st.button("Submit Rating ✅"):
                b_data = b_rows.iloc[0]
                worksheet.append_row([str(chosen), "New Flavor", "", str(b_data['Address']), float(b_data['lat']), float(b_data['lon']), "", str(b_data['Neighborhood']), "User", float(score), ""])
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("Confirm Wishlist ❤️"):
                b_data = b_rows.iloc[0]
                worksheet.append_row([str(chosen), "Wishlist", "", str(b_data['Address']), float(b_data['lat']), float(b_data['lon']), "", str(b_data['Neighborhood']), "User", 0.1, ""])
                st.cache_data.clear(); st.rerun()

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2 = st.tabs(["📍 Map View", "📝 Progress List"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < rating < 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        folium.Marker([coords['lat'], coords['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        clicked = m_out["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Bakery Status Overview")
    list_data = []
    for n in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 0.2 else "⭕ To Visit"
        list_data.append({"Status": s, "Bakery": n})
    
    # We use st.dataframe instead of st.table to prevent the Arrow error
    st.dataframe(pd.DataFrame(list_data), use_container_width=True, hide_index=True)
