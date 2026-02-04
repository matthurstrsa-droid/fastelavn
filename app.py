import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# Source of truth for selection
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

# --- 2. SIDEBAR (The Control Panel) ---
with st.sidebar:
    st.header("⭐ Rate or Wishlist")
    
    # Selection Sync
    options = sorted(df_clean['Bakery Name'].unique().tolist())
    current_idx = options.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in options else 0
    
    # Manual Bakery Selection
    chosen_bakery = st.selectbox("Select Bakery", options, index=current_idx, key="sidebar_selector")
    
    # Ensure session state stays in sync with manual dropdown changes
    if chosen_bakery != st.session_state.selected_bakery:
        st.session_state.selected_bakery = chosen_bakery

    # Get data for selected bakery
    b_rows = df_clean[df_clean['Bakery Name'] == chosen_bakery]
    
    if not b_rows.empty:
        # Flavor Logic
        flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f])
        f_sel = st.selectbox("Flavor", flavs + ["➕ New..."], key=f"f_list_{chosen_bakery}")
        f_name = st.text_input("New flavor name:") if f_sel == "➕ New..." else f_sel
        
        st.divider()
        
        # ACTION CHOICE
        is_already_wish = (0.05 <= bakery_status.get(chosen_bakery, 0) <= 0.2)
        
        # User chooses the mode
        action_mode = st.radio("What's the plan?", ["Rate it", "Add to Wishlist"], 
                               index=1 if is_already_wish else 0,
                               key=f"mode_{chosen_bakery}")

        if action_mode == "Rate it":
            score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
            submit_label = "Submit Rating ✅"
        else:
            score = 0.1
            submit_label = "Add to Wishlist ❤️"
            st.caption("This will mark it Red on the map.")

        if st.button(submit_label):
            b_data = b_rows.iloc[0]
            worksheet.append_row([
                chosen_bakery, f_name, "", b_data['Address'], 
                b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], 
                "User", score, ""
            ])
            st.success("Updated!")
            st.cache_data.clear()
            st.rerun()

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
tab1, tab2 = st.tabs(["📍 Map View", "📝 Checklist"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        row = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        # Icon Logic
        if rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.05 <= rating <= 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker(
            location=[row['lat'], row['lon']],
            tooltip=name,
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    # Capture Map Data
    map_data = st_folium(m, width=1100, height=500, key="main_map")
    
    # Sync Map Click back to Sidebar
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with tab2:
    st.subheader("Interactive Checklist")
    # (Checklist logic remains the same, providing a secondary fast-track)
    check_list = [{"Status": ("✅ Tried" if bakery_status.get(n,0) >= 1.0 else "❤️ Wishlist" if 0.05 <= bakery_status.get(n,0) <= 0.2 else "⭕ To Visit"), "Bakery": n} for n in sorted(df_clean['Bakery Name'].unique())]
    
    edited_df = st.data_editor(
        pd.DataFrame(check_list),
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])},
        disabled=["Bakery"], hide_index=True, use_container_width=True, key="list_editor"
    )

    # Check for instant wishlist change in table
    for i, row in edited_df.iterrows():
        if row['Status'] != check_list[i]['Status']:
            target = row['Bakery']
            if row['Status'] == "❤️ Wishlist":
                b_data = df_clean[df_clean['Bakery Name'] == target].iloc[0]
                worksheet.append_row([target, "Wishlist", "", b_data['Address'], b_data['lat'], b_data['lon'], "", b_data['Neighborhood'], "User", 0.1, ""])
                st.cache_data.clear()
                st.rerun()
            else:
                st.session_state.selected_bakery = target
                st.rerun()
