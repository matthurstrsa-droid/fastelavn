import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium

# --- 1. CONNECTION & INITIALIZATION ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

if "gs_client" not in st.session_state:
    try:
        creds_info = st.secrets["connections"]["my_bakery_db"]
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        st.session_state.gs_client = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Failed: {e}"); st.stop()

def get_worksheet():
    sh = st.session_state.gs_client.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    return sh.get_worksheet(0)

@st.cache_data(ttl=5)
def load_bakery_df():
    ws = get_worksheet()
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    # Clean up column names (handles "Price " vs "Price")
    df.columns = [c.strip() for c in df.columns]
    
    # Standardize data types
    numeric_cols = ['Rating', 'Price', 'lat', 'lon']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            df[col] = 0.0
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. CALCULATE STATS ---
# Only include real ratings (ignore 0.0 and wishlist 0.1)
rated_only = df_clean[df_clean['Rating'] >= 1.0]

if not rated_only.empty:
    stats = rated_only.groupby('Bakery Name').agg({
        'Rating': ['mean', 'count'],
        'Price': 'mean'
    })
    stats.columns = ['Avg_Rating', 'Rating_Count', 'Avg_Price']
    
    # Calculate Best Value
    value_eligible = stats[stats['Avg_Price'] > 0].copy()
    if not value_eligible.empty:
        # Higher score is better value
        value_eligible['Value_Score'] = value_eligible['Avg_Rating'] / value_eligible['Avg_Price']
        best_value_bakery = value_eligible['Value_Score'].idxmax()
    else:
        best_value_bakery = None
    
    top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()
else:
    stats = pd.DataFrame()
    best_value_bakery = None
    top_3 = []

bakery_max_rating = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    with st.expander("🔍 Filters", expanded=True):
        max_p = int(df_clean['Price'].max()) if not df_clean.empty else 100
        p_range = st.slider("Price Range (DKK)", 0, max(100, max_p), (0, max(100, max_p)))
        min_r = st.slider("Min Rating", 1.0, 5.0, 1.0, 0.25)

    # Filter Logic
    def is_visible(name):
        if name not in stats.index: return True # Show unrated/wishlist
        ar, ap = stats.loc[name, 'Avg_Rating'], stats.loc[name, 'Avg_Price']
        return (ar >= min_r) and (p_range[0] <= ap <= p_range[1] if ap > 0 else True)

    visible_names = [n for n in df_clean['Bakery Name'].unique() if is_visible(n)]
    display_df = df_clean[df_clean['Bakery Name'].isin(visible_names)]

    # Actions
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_names:
        current_sel = st.session_state.selected_bakery
        idx = all_names.index(current_sel) if current_sel in all_names else 0
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen
        
        # Rating / Wishlist Logic Here...
    
    st.divider()
    with st.expander("🐞 Data Debugger"):
        st.write("Columns:", list(df.columns))
        st.write("Rated Bakeries:", len(stats))
        if best_value_bakery:
            st.success(f"Best Value: {best_value_bakery}")

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        # Color/Icon Priority
        if name == best_value_bakery: 
            color, icon = "orange", "usd" # Money bag/USD symbol
        elif name in top_3: 
            color = ["beige", "lightgray", "darkred"][top_3.index(name)]
            icon = "star"
        elif max_r >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < max_r < 1.0: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        
        folium.Marker([row['lat'], row['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    st_folium(m, width=1100, height=5
