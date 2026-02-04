import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONNECTION & LOADING ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# Persistent Auth
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

value_stats = stats[stats['Avg_Price'] > 0].copy()
best_value_bakery = value_stats['Avg_Rating'].div(value_stats['Avg_Price']).idxmax() if not value_stats.empty else None
top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()
bakery_max_rating = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR (Fixed for Responsiveness) ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    # Selection logic that won't break on map clicks
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    target = st.session_state.get("selected_bakery")
    idx = all_names.index(target) if target in all_names else 0
    chosen = st.selectbox("Select Bakery", all_names, index=idx, key="bakery_selector")
    
    # Sync choice back to session state
    st.session_state.selected_bakery = chosen

    b_rows = df_clean[df_clean['Bakery Name'] == chosen]
    
    # RESTORED FLAVORS (Always visible)
    existing_flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f and str(f).strip()])
    f_sel = st.selectbox("Flavor", existing_flavs + ["➕ New..."], key=f"flav_sel_{chosen}")
    f_name = st.text_input("Flavor name:", key="new_flav_input") if f_sel == "➕ New..." else f_sel

    mode = st.radio("Action", ["Rate it", "Wishlist"], key="action_mode")
    
    if mode == "Rate it":
        score = st.slider("Rating", 1.0, 5.0, 4.0, 0.25)
        price = st.number_input("Price (DKK)", 0, 200, 45)
        if st.button("Submit Review ✅", use_container_width=True):
            get_worksheet().append_row([chosen, f_name, "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", score, price], value_input_option='USER_ENTERED')
            st.cache_data.clear(); st.rerun()
    else:
        if st.button("Add to Wishlist ❤️", use_container_width=True):
            get_worksheet().append_row([chosen, "Wishlist", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, 0], value_input_option='USER_ENTERED')
            st.cache_data.clear(); st.rerun()

    st.divider()
    with st.expander("🔍 Map Filters"):
        max_p = int(df_clean['Price'].max()) if not df_clean.empty else 100
        p_range = st.slider("Price", 0, max(100, max_p), (0, max(100, max_p)))
        m_rate = st.slider("Min Rating", 1.0, 5.0, 1.0, 0.25)

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])



with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    # Filter display names based on Sidebar sliders
    def is_visible(name):
        if name not in stats.index: return True
        return (stats.loc[name, 'Avg_Rating'] >= m_rate) and (p_range[0] <= stats.loc[name, 'Avg_Price'] <= p_range[1])

    for name in [n for n in df_clean['Bakery Name'].unique() if is_visible(n)]:
        row = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        if name == best_value_bakery: color, icon = "orange", "usd" # "usd" is the money symbol in Bootstrap
        elif name in top_3:
            rank = top_3.index(name); color = ["beige", "lightgray", "darkred"][rank]; icon = "star"
        elif max_r >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < max_r < 1.0: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
            
        folium.Marker([row['lat'], row['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    # Map click capture with no-loop protection
    map_data = st_folium(m, width=1100, height=500, key="main_map")
    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    check_list = [{"Bakery": n, "Status": ("✅ Tried" if bakery_max_rating.get(n,0) >= 1.0 else "❤️ Wishlist" if 0.01 < bakery_max_rating.get(n,0) < 1.0 else "⭕ To Visit"), "Reviews": int(stats.loc[n, 'Rating_Count']) if n in stats.index else 0} for n in sorted(visible_names if 'visible_names' in locals() else all_names)]
    st.dataframe(pd.DataFrame(check_list), use_container_width=True, hide_index=True)

with t3:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏆 Top Rated")
        st.dataframe(stats[['Avg_Rating', 'Rating_Count']].sort_values('Avg_Rating', ascending=False))
    with c2:
        st.subheader("💰 Best Value")
        if best_value_bakery:
            st.metric(best_value_bakery, f"{stats.loc[best_value_bakery, 'Avg_Rating']:.2f} Stars", delta=f"{stats.loc[best_value_bakery, 'Avg_Price']:.0f} DKK")
