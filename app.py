import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import folium
from streamlit_folium import st_folium

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
st.title("🥐 The Ultimate Fastelavnsbolle Map")

# --- 2. AUTHENTICATION & DATA LOADING ---
FOLDER_ID = "1JFp95Kfv7B0FmRgaG0lxntqJz_71muYF"

try:
    # Add DRIVE scope to allow uploading files
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file"
    ]
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    
    # GSheets Client
    gc = gspread.authorize(credentials)
    sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.get_worksheet(0)
    
    # GDrive Client (for photo uploads)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
    df = df.dropna(subset=['lat', 'lon'])

except Exception as e:
    st.error(f"Login or Data Error: {e}")
    st.stop()

# --- 3. SIDEBAR: SUBMIT RATING & PHOTO ---
with st.sidebar:
    st.header("⭐ Rate a Flavour")
    if not df.empty:
        bakery_list = sorted(df['Bakery Name'].unique())
        bakery_choice = st.selectbox("Which bakery?", bakery_list)
        
        existing_flavors = df[df['Bakery Name'] == bakery_choice]['Fastelavnsbolle Type'].unique().tolist()
        existing_flavors = [f for f in existing_flavors if f]
        flavor_options = existing_flavors + ["➕ Add new flavor..."]
        flavor_selection = st.selectbox("Which flavor?", flavor_options)
        
        final_flavor = flavor_selection
        if flavor_selection == "➕ Add new flavor...":
            final_flavor = st.text_input("Type the new flavor name:")

        user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        uploaded_file = st.file_uploader("Upload a photo", type=['jpg', 'png', 'jpeg'])

        if st.button("Submit Rating"):
            if not final_flavor:
                st.error("Please provide a flavor name!")
            else:
                try:
                    photo_url = ""
                    # UPLOAD TO DRIVE LOGIC
                    if uploaded_file:
                        file_metadata = {
                            'name': f"{bakery_choice}_{final_flavor}.jpg",
                            'parents': [FOLDER_ID]
                        }
                        media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), 
                                                  mimetype='image/jpeg')
                        uploaded_drive_file = drive_service.files().create(
                            body=file_metadata, media_body=media, fields='id, webViewLink'
                        ).execute()
                        photo_url = uploaded_drive_file.get('webViewLink')

                    b_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
                    
                    # Appends row to Sheet (Column 11 is now the Photo URL)
                    new_row = [
                        bakery_choice, final_flavor, b_info.get('Price (DKK)', ''),
                        b_info.get('Address', ''), float(b_info['lat']), float(b_info['lon']),
                        b_info.get('Opening Hours', ''), b_info.get('Neighborhood', ''),
                        "App User", user_score, photo_url 
                    ]
                    worksheet.append_row(new_row)
                    st.success(f"Rated {bakery_choice}'s {final_flavor}!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Upload error: {e}")
    else:
        st.warning("No data found.")

# --- 4. MAIN INTERFACE ---
tab1, tab2 = st.tabs(["📍 Bakery Map", "🏆 Leaderboards"])

with tab1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    for _, row in df.iterrows():
        label = f"{row['Bakery Name']} ({row['Fastelavnsbolle Type']})"
        folium.Marker(
            location=[row['lat'], row['lon']], 
            popup=f"Rating: {row['Rating']}/10 - {row['Fastelavnsbolle Type']}",
            tooltip=label
        ).add_to(m)
    st_folium(m, width=900, height=600, key="bakery_map")

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top Bakeries (Overall)")
        bakery_stats = df.groupby('Bakery Name')['Rating'].agg(['mean', 'count']).reset_index()
        bakery_stats.columns = ['Bakery Name', 'Avg Rating', 'Reviews']
        st.dataframe(bakery_stats.sort_values(by="Avg Rating", ascending=False), hide_index=True, use_container_width=True)
    
    with c2:
        st.subheader("Top Specific Flavours")
        flavor_stats = df.groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].agg(['mean', 'count']).reset_index()
        flavor_stats.columns = ['Flavour', 'Bakery', 'Avg Rating', 'Reviews']
        st.dataframe(flavor_stats.sort_values(by="Avg Rating", ascending=False), hide_index=True, use_container_width=True)
