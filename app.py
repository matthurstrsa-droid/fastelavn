import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
st.title("🥐 The Final Bakery Critic")

# --- 2. AUTHENTICATION & DATA LOADING ---
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

    # Convert coordinates to numbers
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
    
    df = df.dropna(subset=['lat', 'lon'])

except Exception as e:
    st.error(f"Login or Data Error: {e}")
    st.stop()

# --- 3. SIDEBAR: SUBMIT RATING ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    if not df.empty:
        # Using your exact column "Bakery Name"
        bakery_list = sorted(df['Bakery Name'].unique())
        bakery_choice = st.selectbox("Which bakery?", bakery_list)
        user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        
        if st.button("Submit Rating"):
            try:
                # Find the existing info to keep the row complete
                b_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
                
                # Append row matching your exact 10 columns:
                # Bakery Name, Fastelavnsbolle Type, Price (DKK), Address, lat, lon, Opening Hours, Neighborhood, Source, Rating
                new_row = [
                    bakery_choice, 
                    b_info.get('Fastelavnsbolle Type', ''),
                    b_info.get('Price (DKK)', ''),
                    b_info.get('Address', ''),
                    float(b_info['lat']), 
                    float(b_info['lon']),
                    b_info.get('Opening Hours', ''),
                    b_info.get('Neighborhood', ''),
                    "App User", # Source
                    user_score   # Rating
                ]
                
                worksheet.append_row(new_row)
                st.success("Rating saved!")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")
    else:
        st.warning("No data found.")

# --- 4. MAIN MAP & LEADERBOARD ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Bakery Map")
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    
    for _, row in df.iterrows():
        # Tooltip shows Name + Type
        label = f"{row['Bakery Name']} ({row['Fastelavnsbolle Type']})"
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"Rating: {row['Rating']}/10 - Price: {row['Price (DKK)']} DKK",
            tooltip=label
        ).add_to(m)

    st_folium(m, width=700, height=500, key="bakery_map")

with col2:
    st.subheader("Leaderboard")
    if not df.empty:
        # Show top rated bakeries
        stats = df.groupby('Bakery Name')['Rating'].mean().reset_index()
        stats = stats.sort_values(by="Rating", ascending=False)
        st.dataframe(stats, use_container_width=True, hide_index=True)
