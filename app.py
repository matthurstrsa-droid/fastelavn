import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONNECTION & LOADING ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

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
    df = pd.DataFrame(ws.get_all_records())
    cols = {'Rating': 0.0, 'Price': 0.0, 'lat': 0.0, 'lon': 0.0, 'Fastelavnsbolle Type': ""}
    for col, default in cols.items():
        if col not in df.columns: df[col] = default
        if col in ['Rating', 'Price', 'lat', 'lon']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. CALCULATE AGGREGATES ---
stats = df_clean[df_clean['Rating'] >= 1.0].groupby('Bakery Name').agg({
    'Rating': ['mean', 'count'],
    'Price': 'mean'
})
stats.columns = ['Avg_Rating', 'Rating_Count', 'Avg_Price']

# Best Value Logic: Highest (Rating / Price) where Price > 0
value_stats = stats[stats['Avg_Price'] > 0].copy()
if not value_stats.empty:
    value_stats['Value_Score'] = value_stats['Avg_Rating'] / value_stats['Avg_Price']
    best_value_bakery = value_stats['Value_Score'].idxmax()
else:
    best_value_bakery = None

top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()
bakery_max_rating = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    with st.expander("🔍 Filters", expanded=True):
        max_p_data = int(df_clean['Price'].max()) if not df_clean.empty else 100
        price_range = st.slider("Price Range (DKK)", 0, max(100, max_p_data), (0, max(100, max_p_data)))
        min_r = st.slider("Min Rating", 1.0, 5.0, 1.0, step=0.25)

    def should_show(name):
        if name not in stats.index: return True
        avg_r, avg_p = stats.loc[name, 'Avg_Rating'], stats.loc[name, 'Avg_Price']
        price_ok = (price_range[0] <= avg_p <= price_range[1]) if avg_p > 0 else True
        return (avg_r >= min_r) and price_ok

    visible_names = [name for name in df_clean['Bakery Name'].unique() if should_show(name)]
    display_df = df_clean[df_clean['Bakery Name'].isin(visible_names)]

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        # ICON LOGIC
        if name == best_value_bakery:
            # Orange marker with a money-bill-wave icon
            color, icon_name, prefix = "orange", "money-bill-wave", "fa"
        elif name in top_3:
            rank = top_3.index(name)
            color = ["beige", "lightgray", "darkred"][rank]
            icon_name, prefix = "star", "fa"
        elif max_r >= 1.0: 
            color, icon_name, prefix = "green", "utensils", "fa"
        elif 0.01 < max_r < 1.0: 
            color, icon_name, prefix = "red", "heart", "fa"
        else: 
            color, icon_name, prefix = "blue", "info-circle", "fa"
            
        folium.Marker(
            [row['lat'], row['lon']], 
            tooltip=name, 
            icon=folium.Icon(color=color, icon=icon_name, prefix=prefix)
        ).add_to(m)
    
    st_folium(m, width=1100, height=500, key="main_map")

with t2:
    st.subheader("Checklist & Stats")
    check_list = [{"Bakery": n, "Status": ("✅ Tried" if bakery_max_rating.get(n,0) >= 1.0 else "❤️ Wishlist" if 0.01 < bakery_max_rating.get(n,0) < 1.0 else "⭕ To Visit"), "Times Rated": int(stats.loc[n, 'Rating_Count']) if n in stats.index else 0} for n in sorted(display_df['Bakery Name'].unique())]
    st.dataframe(pd.DataFrame(check_list), use_container_width=True, hide_index=True)

with t3:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏆 Top Rated")
        st.dataframe(stats[['Avg_Rating', 'Rating_Count']].sort_values('Avg_Rating', ascending=False).rename(columns={"Avg_Rating": "Rating", "Rating_Count": "Reviews"}))
    with c2:
        st.subheader("💰 Best Value")
        if best_value_bakery:
            st.metric(best_value_bakery, f"{stats.loc[best_value_bakery, 'Avg_Rating']:.2f} Stars", 
                      delta=f"Avg: {stats.loc[best_value_bakery, 'Avg_Price']:.0f} DKK")
