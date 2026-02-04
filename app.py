import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v4")

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

# --- 2. PROGRESS LOGIC ---
tried_bakeries = df[df['Rating'] > 0.1]['Bakery Name'].unique().tolist()

# --- 3. SIDEBAR: PROGRESS & SUBMISSION ---
with st.sidebar:
    st.header("📊 Your Progress")
    total_spots = len(df['Bakery Name'].unique())
    visited_spots = len(tried_bakeries)
    st.write(f"Conquered: {visited_spots} / {total_spots}")
    st.progress(visited_spots / total_spots if total_spots > 0 else 0)
    
    st.divider()
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("New Bakery?")
    clicked_bakery = st.session_state.get("clicked_bakery", None)

    # Initialize variables to avoid 'Undefined' errors
    final_lat, final_lon = 0.0, 0.0
    address, neighborhood_input = "", ""

    if is_new_bakery:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address (incl. Copenhagen)")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
    else:
        bakery_options = sorted(df['Bakery Name'].unique())
        default_idx = bakery_options.index(clicked_bakery) if clicked_bakery in bakery_options else 0
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        flavor_selection = st.selectbox("Which flavour?", [f for f in existing_flavs if f] + ["➕ Add new..."], key=f"flav_{bakery_name}")
        flavor_name = st.text_input("Flavor name:") if flavor_selection == "➕ Add new..." else flavor_selection
        
        # FIX: Correctly extracting data from the existing row
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        final_lat = b_info['lat']
        final_lon = b_info['lon']
        address = b_info.get('Address', '')
        neighborhood_input = b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    is_wishlist = st.checkbox("Add to Wishlist? ❤️")
    photo_link = st.text_input("Photo URL")

    if st.button("Submit"):
        try:
            if is_new_bakery:
                with st.spinner("Finding address..."):
                    location = geolocator.geocode(address)
                    if location:
                        final_lat, final_lon = location.latitude, location.longitude
                    else:
                        st.error("Address error")
                        st.stop()
            
            submit_score = 0.1 if is_wishlist else user_score
            
            new_row = [bakery_name, flavor_name, "", address, float(final_lat), float(final_lon), "", neighborhood_input, "User", submit_score, photo_link]
            worksheet.append_row(new_row)
            st.success("Updated!")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# --- 4. MAIN UI ---
st.title("🥐 Fastelavnsbolle Explorer")

all_n = ["All"] + sorted([n for n in df['Neighborhood'].unique() if n])
selected_n = st.selectbox("Filter Neighborhood", all_n)
display_df = df if selected_n == "All" else df[df['Neighborhood'] == selected_n]

tab1, tab2, tab3 = st.tabs(["📍 Map View", "📝 Checklist", "🏆 Rankings"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for _, row in display_df.iterrows():
        is_tried = row['Bakery Name'] in tried_bakeries
        is_wish = row['Rating'] == 0.1
        
        if is_tried:
            m_color, m_icon = "green", "check"
        elif is_wish:
            m_color, m_icon = "red", "heart"
        else:
            m_color, m_icon = "blue", "info-sign"
        
        photo_val = row.get('PhotoURL', '')
        img_tag = f'<img src="{photo_val}" width="150px" style="border-radius:5px;">' if photo_val else ""
        
        # Display 'Wishlist' instead of '0.1' in the popup
        display_score = f"{row['Rating']}/10" if row['Rating'] > 0.1 else "Wishlist"
        
        popup_html = f"<b>{row['Bakery Name']}</b><br>Score: {display_score}<br>{img_tag}"
        
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=row['Bakery Name'],
            icon=folium.Icon(color=m_color, icon=m_icon)
        ).add_to(m)
    
    map_data = st_folium(m, width=1000, height=500, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        st.session_state.clicked_bakery = map_data["last_object_clicked_tooltip"]

with tab2:
    st.subheader("Your Bakery Checklist")
    checklist_df = display_df.groupby('Bakery Name').agg({
        'Neighborhood': 'first',
        'Rating': 'max'
    }).reset_index()
    
    def get_status(rating):
        if rating > 0.1: return "✅ Tried"
        if rating == 0.1: return "❤️ Wishlist"
        return "⭕ To Visit"

    checklist_df['Status'] = checklist_df['Rating'].apply(get_status)
    st.dataframe(checklist_df[['Status', 'Bakery Name', 'Neighborhood']].sort_values('Status'), use_container_width=True, hide_index=True)

with tab3:
    c1, c2 = st.columns(2)
    valid_ratings = display_df[display_df['Rating'] > 0.1]
    with c1:
        st.subheader("Top Bakeries")
        if not valid_ratings.empty:
            st.dataframe(valid_ratings.groupby('Bakery Name')['Rating'].agg(['mean', 'count']).sort_values('mean', ascending=False), hide_index=True)
    with c2:
        st.subheader("Top Flavours")
        if not valid_ratings.empty:
            st.dataframe(valid_ratings.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].agg(['mean', 'count']).sort_values('mean', ascending=False), hide_index=True)
