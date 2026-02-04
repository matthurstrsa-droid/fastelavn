import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import folium
from streamlit_folium import st_folium

# --- SETUP ---
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# Connect to the Sheet
conn = st.connection("gsheets", type=GSheetsConnection)
url = "fastelavnsbolle_guide_2025"

# Load the data
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo/edit?gid=91624038"
df = conn.read(spreadsheet=sheet_id, worksheet="Sheet1", ttl="0m")

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



