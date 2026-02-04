import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

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

# Status Helper
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 2. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
tab1, tab2 = st.tabs(["📍 Map View", "📝 Interactive Checklist"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        row = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[row['lat'], row['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    map_output = st_folium(m, width=1100, height=450, key="bakery_map")
    if map_output and map_output.get("last_object_clicked_tooltip"):
        clicked = map_output["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with tab2:
    st.subheader("Quick Actions")
    st.write("Change status to **Wishlist** to auto-save, or **Tried** to open the rating form.")
    
    # Prepare data for the editor
    check_list = []
    for name in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(name, 0)
        stat = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.05 <= r <= 0.2 else "⭕ To Visit"
        check_list.append({"Status": stat, "Bakery": name})
    
    display_df = pd.DataFrame(check_list)
    
    # INTERACTIVE TABLE
    edited_df = st.data_editor(
        display_df,
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])},
        disabled=["Bakery"], hide_index=True, use_container_width=True, key="list_editor"
    )

    # ACTION LOGIC
    for i, row in edited_df.iterrows():
        if row['Status'] != display_df.iloc[i]['Status']:
            target = row['Bakery']
            
            if row['Status'] == "❤️ Wishlist":
                # INSTANT SAVE TO SHEET
                b_data = df_clean[df_clean['Bakery Name'] == target].iloc[0]
                worksheet.append_row([target, "Wishlist", "", b_data['Address'], b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], "User", 0.1, ""])
                st.cache_data.clear()
                st.rerun()
            
            elif row['Status'] == "✅ Tried":
                # OPEN SIDEBAR
                st.session_state.selected_bakery = target
                st.rerun()

# --- 3. SIDEBAR (Only for Ratings) ---
with st.sidebar:
    if st.session_state.selected_bakery:
        st.header(f"⭐ Rate: {st.session_state.selected_bakery}")
        b_name = st.session_state.selected_bakery
        b_rows = df_clean[df_clean['Bakery Name'] == b_name]
        
        # Flavor Logic
        flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f])
        f_sel = st.selectbox("Which flavor?", flavs + ["➕ New..."], key=f"f_{b_name}")
        f_name = st.text_input("New flavor name:") if f_sel == "➕ New..." else f_sel
        
        # Rating
        score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        
        if st.button("Submit Rating"):
            b_data = b_rows.iloc[0]
            worksheet.append_row([b_name, f_name, "", b_data['Address'], b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], "User", score, ""])
            st.success("Rated!")
            st.cache_data.clear()
            st.session_state.selected_bakery = None
            st.rerun()
        
        if st.button("Cancel"):
            st.session_state.selected_bakery = None
            st.rerun()
    else:
        st.info("Select a bakery from the Map or Checklist to start rating!")
