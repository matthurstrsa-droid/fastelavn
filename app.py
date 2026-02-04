import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. PAGE SETUP ---
# This must be the very first Streamlit command
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- CONNECTION ---
# We force the connection to use the service account
conn = st.connection("gsheets", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

# Load data
df = conn.read(spreadsheet=sheet_id, ttl="0m")
df.columns = df.columns.str.strip()

# --- INSIDE THE RATING BUTTON ---
if st.button("Submit Rating"):
    bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
    
    # Create the new row
    new_row = pd.DataFrame([{
        "Bakery Name": bakery_choice,
        "Fastelavnsbolle Type": bakery_info.get('Fastelavnsbolle Type', ''),
        "Price (DKK)": bakery_info.get('Price (DKK)', 0),
        "Address": bakery_info.get('Address', ''),
        "Opening Hours": bakery_info.get('Opening Hours', ''),
        "Neighborhood": bakery_info.get('Neighborhood', ''),
        "Source": bakery_info.get('Source', ''),
        "Rating": user_score
    }])

    try:
        # Use the specialized .update() method for the connection
        # We combine the old data with the new row
        updated_df = pd.concat([df, new_row], ignore_index=True)
        
        # This is the 'Secret Sauce' call
        conn.update(spreadsheet=sheet_id, data=updated_df)
        
        st.success(f"Rating for {bakery_choice} saved!")
        st.balloons()
        st.rerun()
    except Exception as e:
        st.error(f"Write failed: {e}")
        st.info("Check if your Service Account email has 'Editor' access in Google Sheets!")
# --- 4. MAIN INTERFACE: MAP & LEADERBOARD ---

# Calculate average ratings


