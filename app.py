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
    # This pulls from your [connections.my_bakery_db] secrets
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    
    # Open the sheet
    sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.get_worksheet(0)
    
    # Load data
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    # --- DATA SANITIZER ---
    # This fixes the "ValueError" by forcing coordinates to be actual numbers
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    # Remove any rows where lat/lon is missing or broken
    df = df.dropna(subset=['lat', 'lon'])

except Exception as e:
    st.error(f"Login or Data Error: {e}")
    st.stop()

# --- 3. SIDEBAR: SUBMIT RATING ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    if not df.empty:
        bakery_list = sorted(df['Bakery Name'].unique())
        bakery_choice = st.selectbox("Which bakery?", bakery_list)
        user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        
        if st.button("Submit Rating"):
            try:
                # Find the coords for the selected bakery
                bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
                
                # Append to Google Sheet
                worksheet.append_row([
                    bakery_choice, 
                    user_score, 
                    float(bakery_info['lat']), 
                    float(bakery_info['lon'])
                ])
                st.success("Rating saved!")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")
    else:
        st.warning("No bakeries found in the sheet.")

# --- 4. MAIN MAP & LEADERBOARD ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Bakery Map")
    # Center map on Copenhagen
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    
    # Add markers only for valid rows
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"{row['Bakery Name']}: {row['Rating']}/10",
            tooltip=row
