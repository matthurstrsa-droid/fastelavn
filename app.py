import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. PAGE SETUP ---
# This must be the very first Streamlit command
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# --- 2. THE CONNECTION ---
# Looks for [connections.gsheets] in your Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# Your specific Google Sheet ID
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

try:
    # Attempt to read data using your Service Account credentials
    df = conn.read(spreadsheet=sheet_id, ttl="0m")
    
    # Clean up column names (removes accidental spaces)
    df.columns = df.columns.str.strip()
    
    # Check for required columns to prevent crashes
    required_columns = ['Bakery Name', 'Rating', 'lat', 'lon']
    for col in required_columns:
        if col not in df.columns:
            st.error(f"Missing column: '{col}'. Found: {list(df.columns)}")
            st.stop()

except Exception as e:
    st.error("🔒 Authentication Failed or Sheet Not Found.")
    st.info("Make sure your Secrets are filled and the Service Account email is an Editor on the Google Sheet.")
    st.exception(e) # This shows the technical error for debugging
    st.stop()

# --- 3. SIDEBAR: RATING FUNCTION ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    
    # Create dropdown from existing bakeries
    bakery_choice = st.selectbox("Which bakery did you visit?", df['Bakery Name'].unique())
    
    # Rating inputs
    user_score = st.slider("Your Rating (1-10)", 1.0, 10.0, 8.0, step=0.5)
    user_comment = st.text_input("Short comment (optional)")
    
    if st.button("Submit Rating"):
        # Get data for the selected bakery
        bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
        
        # Prepare the new row
        new_row = pd.DataFrame([{
            "Bakery Name": bakery_choice,
            "Fastelavnsbolle Type": bakery_info.get('Fastelavnsbolle Type', 'Unknown'),
            "Price (DKK)": bakery_info.get('Price (DKK)', 0),
            "Address": bakery_info.get('Address', ''),
            "Rating": user_score,
            "lat": bakery_info['lat'],
            "lon": bakery_info['lon']
        }])
        
        # Add to existing data
        updated_df = pd.concat([df, new_row], ignore_index=True)
        
        # Write back to Google Sheets
        conn.update(spreadsheet=sheet_id, data=updated_df)
        
        st.success(f"Rating for {bakery_choice} saved!")
        st.balloons()
        st.rerun()

# --- 4. MAIN INTERFACE: MAP & LEADERBOARD ---

# Calculate average ratings
