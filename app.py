import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# --- 2. THE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

try:
    # Load and clean data
    df = conn.read(spreadsheet=sheet_id, ttl="0m")
    df.columns = df.columns.str.strip()
    
    # --- ADD THIS LINE HERE ---
    df = df.dropna(subset=['Bakery Name']) 
    # --------------------------

    # Ensure required columns exist
    required = ['Bakery Name', 'Rating', 'lat', 'lon']
    # ... rest of your code
except Exception as e:
    st.error(f"Authentication Failed: {e}")
    st.stop()

# --- 3. SIDEBAR: RATING FUNCTION ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    
    # Define bakery_choice HERE so the button can see it
    bakery_choice = st.selectbox("Which bakery did you visit?", df['Bakery Name'].unique())
    user_score = st.slider("Your Rating", 1.0, 10.0, 8.0, step=0.5)
    
    if st.button("Submit Rating"):
        # Get bakery info for the selection
        bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
        
        new_row = pd.DataFrame([{
            "Bakery Name": bakery_choice,
            "Fastelavnsbolle Type": bakery_info.get('Fastelavnsbolle Type', ''),
            "Price (DKK)": bakery_info.get('Price (DKK)', 0),
            "Address": bakery_info.get('Address', ''),
            "Opening Hours": bakery_info.get('Opening Hours', ''),
            "Neighborhood": bakery_info.get('Neighborhood', ''),
            "Source": bakery_info.get('Source', ''),
            "Rating": user_score,
            "lat": bakery_info['lat'],
            "lon": bakery_info['lon']
        }])
        
        try:
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(spreadsheet=sheet_id, data=updated_df)
            st.success("Saved! Refreshing...")
            st.balloons()
            st.rerun()
        except Exception as e:
            st.error(f"Error saving: {e}")

# --- 4. MAIN INTERFACE ---
avg_ratings = df.groupby('Bakery Name')['Rating'].mean().reset_index()
col_map, col_list = st.columns([2, 1])

with col_map:
    st.subheader("📍 Bakery Map")
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12)
    map_data = df.drop_duplicates(subset=['Bakery Name'])
    
    for _, row in map_data.iterrows():
        score = avg_ratings[avg_ratings['Bakery Name'] == row['Bakery Name']]['Rating'].values[0]
        folium.Marker(
            [row['lat'], row['lon']],
            popup=f"<b>{row['Bakery Name']}</b><br>Rating: {score:.1f}",
            tooltip=row['Bakery Name']
        ).add_to(m)
    st_folium(m, width="100%", height=500)

with col_list:
    st.subheader("🏆 Top Rated")
    top_buns = avg_ratings.sort_values(by="Rating", ascending=False)
    st.dataframe(top_buns, hide_index=True, use_container_width=True)


