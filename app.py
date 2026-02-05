import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. SETUP (Optimized Cache) ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_resource
def get_gs_client():
    creds_info = st.secrets["connections"]["my_bakery_db"]
    creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)

@st.cache_data(ttl=300) # Increased to 5 minutes for speed; use a Refresh button to force update
def load_bakery_df():
    client = get_gs_client()
    sh = client.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    df = pd.DataFrame(sh.get_worksheet(0).get_all_records())
    df.columns = [c.strip() for c in df.columns]
    for col in ['Rating', 'Price', 'lat', 'lon']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

# Fast load
df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 2. FAST STATS ---
# Pre-calculate once per rerun
rated_only = df_clean[df_clean['Rating'] >= 1.0]
stats = pd.DataFrame()
best_value_bakery = None
top_3 = []

if not rated_only.empty:
    stats = rated_only.groupby('Bakery Name').agg({'Rating': ['mean', 'count'], 'Price': 'mean'})
    stats.columns = ['Avg_Rating', 'Rating_Count', 'Avg_Price']
    
    val_stats = stats[stats['Avg_Price'] > 0].copy()
    if not val_stats.empty:
        val_stats['Val'] = val_stats['Avg_Rating'] / val_stats['Avg_Price']
        best_value_bakery = val_stats['Val'].idxmax()
    top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()

bakery_max_rating = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    # Add a Manual Refresh button since we increased cache time
    if st.button("🔄 Sync with Google Sheets"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("🔍 Map Filters"):
        max_p = int(df_clean['Price'].max()) if not df_clean.empty else 100
        p_range = st.slider("Price (DKK)", 0, max(100, max_p), (0, max(100, max_p)))
        min_r = st.slider("Min Rating", 1.0, 5.0, 1.0, 0.25)

    # Fast visibility check
    def is_visible(name):
        if name == best_value_bakery: return True
        if name in stats.index:
            avg_r, avg_p = stats.loc[name, 'Avg_Rating'], stats.loc[name, 'Avg_Price']
            return (avg_r >= min_r) and ((p_range[0] <= avg_p <= p_range[1]) if avg_p > 0 else True)
        return True

    visible_names = [n for n in df_clean['Bakery Name'].unique() if is_visible(n)]
    display_df = df_clean[df_clean['Bakery Name'].isin(visible_names)]

    st.divider()
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    sel = st.session_state.selected_bakery
    idx = all_names.index(sel) if sel in all_names else 0
    chosen = st.selectbox("Select Bakery", all_names, index=idx)
    st.session_state.selected_bakery = chosen
    
    # Rest of the flavor/rating UI... (Keep same as before)

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    # Set a static starting point for the map so it doesn't "reset" zoom awkwardly
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=12, tiles="CartoDB positron")
    
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        # Icon Priority
        if name == best_value_bakery: color, icon = "orange", "usd"
        elif name in top_3: color, icon = ["beige", "lightgray", "darkred"][top_3.index(name)], "star"
        elif max_r >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < max_r < 1.0: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        
        folium.Marker(
            [row['lat'], row['lon']], 
            tooltip=name, 
            icon=folium.Icon(color=color, icon=icon)
        ).add_to(m)
    
    # st_folium with returned_objects=[] speeds up the component drastically
    map_output = st_folium(m, width=1100, height=500, key="main_map")
    
    if map_output and map_output.get("last_object_clicked_tooltip"):
        clicked = map_output["last_object_clicked_tooltip"]
        if clicked != st.session_state.selected_bakery:
            st.session_state.selected_bakery = clicked
            st.rerun()

# Checklist and Podium remain the same...
