import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v6")

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

# --- 2. UNIFIED PROGRESS LOGIC ---
# Group by bakery to get the highest status
bakery_status = df.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR: PROGRESS & SUBMISSION ---
with st.sidebar:
    st.header("📊 Your Progress")
    tried_count = sum(1 for r in bakery_status.values() if r > 0.1)
    total_count = len(bakery_status)
    st.write(f"Conquered: {tried_count} / {total_count}")
    st.progress(tried_count / total_count if total_count > 0 else 0)
    
    st.divider()
    st.header("⭐ Rate or Add")
    
    is_new_bakery = st.checkbox("New Bakery?")
    
    # Listen to Map or Checklist interaction
    target_bakery = st.session_state.get("list_selection") or st.session_state.get("clicked_bakery")

    if is_new_bakery:
        bakery_name = st.text_input("Bakery Name")
        flavor_name = st.text_input("Flavor Name")
        address = st.text_input("Address (incl. Copenhagen)")
        neighborhood_input = st.selectbox("Neighborhood", ["Vesterbro", "Nørrebro", "Østerbro", "Indre By", "Frederiksberg", "Amager", "Other"])
    else:
        bakery_options = sorted(df['Bakery Name'].unique())
        default_idx = bakery_options.index(target_bakery) if target_bakery in bakery_options else 0
        bakery_name = st.selectbox("Which bakery?", bakery_options, index=default_idx)
        
        existing_flavs = sorted(df[df['Bakery Name'] == bakery_name]['Fastelavnsbolle Type'].unique().tolist())
        flavor_selection = st.selectbox("Which flavour?", [f for f in existing_flavs if f] + ["➕ Add new..."], key=f"flav_{bakery_name}")
        flavor_name = st.text_input("Flavor name:") if flavor_selection == "➕ Add new..." else flavor_selection
        
        b_info = df[df['Bakery Name'] == bakery_name].iloc[0]
        final_lat, final_lon = b_info['lat'], b_info['lon']
        address, neighborhood_input = b_info.get('Address', ''), b_info.get('Neighborhood', '')

    user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
    is_wishlist = st.checkbox("Add to Wishlist? ❤️")
    photo_link = st.text_input("Photo URL")

    if st.button("Submit"):
        try:
            if is_new_bakery:
                location = geolocator.geocode(address)
                if location:
                    final_lat, final_lon = location.latitude, location.longitude
                else:
                    st.error("Address error"); st.stop()
            
            submit_score = 0.1 if is_wishlist else user_score
            new_row = [bakery_name, flavor_name, "", address, float(final_lat), float(final_lon), "", neighborhood_input, "User", submit_score, photo_link]
            worksheet.append_row(new_row)
            st.success("Updated!"); st.session_state.list_selection = None; st.rerun()
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
    for name, rating in bakery_status.items():
        # Get one row for this bakery for its lat/lon
        row = df[df['Bakery Name'] == name].iloc[0]
        
        # Icon Logic
        if rating > 0.1:
            m_color, m_icon = "green", "cutlery"
        elif rating == 0.1:
            m_color, m_icon = "red", "heart"
        else:
            m_color, m_icon = "blue", "info-sign"
        
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"{name} ({'Wishlisted' if rating == 0.1 else str(rating)+'/10'})",
            tooltip=name,
            icon=folium.Icon(color=m_color, icon=m_icon)
        ).add_to(m)
    
    map_data = st_folium(m, width=1000, height=500, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        st.session_state.clicked_bakery = map_data["last_object_clicked_tooltip"]

with tab2:
    st.subheader("Interactive Checklist")
    # Build clean display list
    checklist_data = []
    for name in sorted(df['Bakery Name'].unique()):
        rating = bakery_status.get(name, 0)
        status = "✅ Tried" if rating > 0.1 else "❤️ Wishlist" if rating == 0.1 else "⭕ To Visit"
        hood = df[df['Bakery Name'] == name]['Neighborhood'].iloc[0]
        checklist_data.append({"Status": status, "Bakery Name": name, "Neighborhood": hood})
    
    check_df = pd.DataFrame(checklist_data)
    
    edited_df = st.data_editor(
        check_df,
        column_config={
            "Status": st.column_config.SelectboxColumn("Action", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])
        },
        disabled=["Bakery Name", "Neighborhood"],
        hide_index=True, use_container_width=True, key="ce"
    )

    # Trigger Sidebar or Auto-Wishlist
    for idx, row in edited_df.iterrows():
        if row['Status'] != check_df.iloc[idx]['Status']:
            if row['Status'] == "✅ Tried":
                st.session_state.list_selection = row['Bakery Name']
                st.rerun()
            elif row['Status'] == "❤️ Wishlist":
                b_row = df[df['Bakery Name'] == row['Bakery Name']].iloc[0]
                worksheet.append_row([row['Bakery Name'], "Wishlist", "", b_row['Address'], b_row['lat'], b_row['lon'], "", b_row['Neighborhood'], "User", 0.1, ""])
                st.rerun()

with tab3:
    valid = display_df[display_df['Rating'] > 0.1]
    if not valid.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Bakeries")
            st.dataframe(valid.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False))
        with c2:
            st.subheader("Top Flavours")
            st.dataframe(valid.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False))
