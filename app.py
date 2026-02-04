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
        # 1. Choose Bakery
        bakery_list = sorted(df['Bakery Name'].unique())
        bakery_choice = st.selectbox("Which bakery?", bakery_list)
        
        # 2. Get existing flavors for THIS bakery only
        existing_flavors = df[df['Bakery Name'] == bakery_choice]['Fastelavnsbolle Type'].unique().tolist()
        existing_flavors = [f for f in existing_flavors if f] # Remove empty ones
        
        # Add a special "Other" option
        flavor_options = existing_flavors + ["➕ Add new flavor..."]
        flavor_selection = st.selectbox("Which flavor?", flavor_options)
        
        # 3. If they chose "Add new", show a text box
        final_flavor = flavor_selection
        if flavor_selection == "➕ Add new flavor...":
            final_flavor = st.text_input("Type the new flavor name:")

        user_score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        
        if st.button("Submit Rating"):
            if not final_flavor:
                st.error("Please provide a flavor name!")
            else:
                try:
                    b_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
                    
                    new_row = [
                        bakery_choice, 
                        final_flavor,       # Uses the dropdown OR the text box
                        b_info.get('Price (DKK)', ''),
                        b_info.get('Address', ''),
                        float(b_info['lat']), 
                        float(b_info['lon']),
                        b_info.get('Opening Hours', ''),
                        b_info.get('Neighborhood', ''),
                        "App User", 
                        user_score   
                    ]
                    
                    worksheet.append_row(new_row)
                    st.success(f"Rated {bakery_choice}'s {final_flavor}!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Save error: {e}")
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

