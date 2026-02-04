import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import folium
from streamlit_folium import st_folium

# --- SETUP ---
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# 1. Start the connection (uses the secrets labeled [connections.gsheets])
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. Point to your specific sheet ID
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

# --- 1. THE LOADING SECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

# We use a try/except block to catch errors gracefully
try:
    df = conn.read(spreadsheet=sheet_id, ttl="0m")
    
    # CLEANING: This removes any accidental hidden spaces in your headers
    df.columns = df.columns.str.strip()
    
    # DEBUG: This will show you exactly what your columns are named in a little box
    st.info(f"Successfully loaded! Column names found: {list(df.columns)}")

except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop() # Stops the app here so we don't get the line 28 error
# --- SIDEBAR: RATING FUNCTION ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    # Dropdown based on your existing sheet names
    bakery_choice = st.selectbox("Which bakery did you visit?", df['Bakery Name'].unique())
    
    # Rating sliders
    user_score = st.slider("Your Rating", 1.0, 10.0, 8.0, step=0.5)
    user_comment = st.text_input("Short comment (optional)")
    
    if st.button("Submit Rating"):
        # Create a new row with the same columns as your sheet
        # We fill non-rating columns with the existing data for that bakery
        bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
        
        new_row = pd.DataFrame([{
            "Bakery Name": bakery_choice,
            "Fastelavnsbolle Type": bakery_info['Fastelavnsbolle Type'],
            "Price (DKK)": bakery_info['Price (DKK)'],
            "Address": bakery_info['Address'],
            "Rating": user_score,
            "lat": bakery_info['lat'], # Assumes you added these columns
            "lon": bakery_info['lon']
        }])
        
        # WRITE to the Google Sheet
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(spreadsheet=url, data=updated_df)
        
        st.success(f"Rating for {bakery_choice} saved! Refreshing...")
        st.rerun()

# --- MAIN: MAP & LEADERBOARD ---
# We calculate the average rating per bakery for the map popups
avg_ratings = df.groupby('Bakery Name')['Rating'].mean().reset_index()

col_map, col_list = st.columns([2, 1])

with col_map:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    # Use unique bakeries for map pins to avoid overlapping duplicates
    map_data = df.drop_duplicates(subset=['Bakery Name'])
    
    for _, row in map_data.iterrows():
        # Get the average for this specific bakery
        score = avg_ratings[avg_ratings['Bakery Name'] == row['Bakery Name']]['Rating'].values[0]
        
        folium.Marker(
            [row['lat'], row['lon']],
            popup=f"<b>{row['Bakery Name']}</b><br>Avg Rating: {score:.1f}/10",
            tooltip=row['Bakery Name']
        ).add_to(m)
    st_folium(m, width="100%", height=500)

with col_list:
    st.subheader("🏆 Top Rated Buns")
    top_buns = avg_ratings.sort_values(by="Rating", ascending=False)
    st.dataframe(top_buns, hide_index=True)












