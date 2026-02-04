import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Bakery Critic", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# Use the name that matches your secrets header: [connections.my_bakery_db]
conn = st.connection("bakery_final_fix", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

# --- 2. DATA LOADING ---
try:
    # ttl=0 is vital here to bypass the "Response 200" ghost cache
    df = conn.read(spreadsheet=sheet_id, ttl=0)
    
    # If df is somehow not a dataframe, force it to be one or show error
    if not isinstance(df, pd.DataFrame):
        st.error("Google sent a webpage instead of data. Try: Share -> Add Service Account as Editor.")
        st.stop()

    df = df.dropna(subset=['lat', 'lon'])
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.info("Check that 'General Access' is Restricted and the Service Account is an Editor.")
    st.stop()

# --- 3. SIDEBAR: RATING FORM ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    
    # Dropdown of bakeries from your sheet
    bakery_list = df['Bakery Name'].unique()
    bakery_choice = st.selectbox("Which bakery did you visit?", bakery_list)
    
    # User selects a rating
    user_score = st.slider("Your Rating", 1.0, 10.0, 8.0, step=0.5)
    
    if st.button("Submit Rating", key="submit_btn"):
        # Get the lat/lon of the chosen bakery to keep the data consistent
        bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
        
        # Create a new row
        new_row = pd.DataFrame([{
            "Bakery Name": bakery_choice,
            "Rating": user_score,
            "lat": bakery_info['lat'],
            "lon": bakery_info['lon']
        }])
        
        try:
            # Append new row to existing data
            updated_df = pd.concat([df, new_row], ignore_index=True)
            
            # Write back to Google Sheets
            conn.update(spreadsheet=sheet_id, data=updated_df)
            
            st.success(f"Rating for {bakery_choice} saved!")
            st.balloons()
            
            # Clear cache and refresh app to show new data
            st.cache_data.clear()
            st.rerun()
            
        except Exception as e:
            st.error(f"Error saving to sheet: {e}")
            st.info("Check that your Service Account email is an 'Editor' on the Google Sheet.")

# --- 4. MAIN INTERFACE: MAP & LEADERBOARD ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Bakery Map")
    # Initialize Map
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    
    # Add markers for every bakery in the sheet
    for index, row in df.iterrows():
        folium.Marker(
            [row['lat'], row['lon']],
            popup=f"{row['Bakery Name']}: {row['Rating']}/10",
            tooltip=row['Bakery Name']
        ).add_to(m)
    
    # Display the map
    st_folium(m, width=700, height=500, returned_objects=[])

with col2:
    st.subheader("Top Rated")
    # Show top 10 bakeries sorted by rating
    leaderboard = df.sort_values(by="Rating", ascending=False).head(10)
    st.table(leaderboard[['Bakery Name', 'Rating']])


