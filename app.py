import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. AUTHENTICATION ---
# This pulls the "Flat" secrets we set up earlier
try:
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    # We rebuild the credentials object from your secrets
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)
    
    # Open the sheet by its ID
    sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.get_worksheet(0) # Opens the first tab
    
   # Load data into DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    # --- NEW: CLEAN THE DATA ---
    # 1. Convert lat/lon to numbers (in case Google sent them as strings)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

    # 2. Drop any rows that are missing coordinates
    df = df.dropna(subset=['lat', 'lon'])
# --- 2. APP INTERFACE ---
st.title("🥐 The Final Bakery Critic")

# Sidebar for rating
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    bakery_choice = st.selectbox("Bakery", df['Bakery Name'].unique())
    user_score = st.slider("Rating", 1.0, 10.0, 8.0)
    
    if st.button("Submit"):
        try:
            # Add a new row to the bottom of the sheet
            bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
            worksheet.append_row([bakery_choice, user_score, bakery_info['lat'], bakery_info['lon']])
            st.success("Saved!")
            st.rerun()
        except Exception as e:
            st.error(f"Save error: {e}")

# --- 3. THE MAP ---
m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
for _, row in df.iterrows():
    folium.Marker([row['lat'], row['lon']], popup=row['Bakery Name']).add_to(m)

st_folium(m, width=700)

