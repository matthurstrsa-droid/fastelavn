import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- FORCE NEW CONNECTION NAME ---
# We change "gsheets" to "my_bakery_db" to clear any bad cache
conn = st.connection("my_bakery_db", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Fastelavnsbolle 2026", layout="wide")
st.title("🥐 The Community Fastelavnsbolle Critic")

# --- 2. THE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)
sheet_id = "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"

try:
    # Load and clean data
    df = conn.read(spreadsheet=sheet_id, ttl="1m")
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
# --- 3. SIDEBAR: RATING FUNCTION ---
with st.sidebar:
    st.header("⭐ Rate a Bakery")
    
    # This defines the dropdown and the slider
    bakery_choice = st.selectbox("Which bakery did you visit?", df['Bakery Name'].unique())
    user_score = st.slider("Your Rating", 1.0, 10.0, 8.0, step=0.5)
    
    # --- THIS IS THE SUBMIT RATING BLOCK ---
    if st.button("Submit Rating", key="submit_btn"):
        bakery_info = df[df['Bakery Name'] == bakery_choice].iloc[0]
        
        # We create the new row to be added
        new_row = pd.DataFrame([{
            "Bakery Name": bakery_choice,
            "Rating": user_score,
            "lat": bakery_info['lat'],
            "lon": bakery_info['lon']
        }])
        
        try:
            # We combine the existing data with the new row
            updated_df = pd.concat([df, new_row], ignore_index=True)
            
            # This is where the magic happens - writing to Google Sheets
            conn.update(spreadsheet=sheet_id, data=updated_df)
            
            st.success("Saved! Refreshing...")
            st.cache_data.clear() 
            st.rerun()
            
        except Exception as e:
            st.error(f"Error saving: {e}")
    # --- END OF THE BLOCK ---
            
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






