import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONNECTION & LOADING ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# INITIALIZE STATE (Fixes the AttributeError)
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

    st.divider()
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_names:
        # Safe Check for Index
        current_sel = st.session_state.selected_bakery
        idx = all_names.index(current_sel) if current_sel in all_names else 0
        
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen
        
        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        existing_flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f and str(f).strip()])
        f_sel = st.selectbox("Flavor", existing_flavs + ["➕ New..."], key=f"f_sel_{chosen}")
        f_name = st.text_input("New flavor name:", key=f"f_input_{chosen}") if f_sel == "➕ New..." else f_sel

        action = st.radio("Mode:", ["Rate it", "Wishlist"], index=0)
        if action == "Rate it":
            score = st.slider("Rating", 1.0, 5.0, 4.0, step=0.25, key=f"r_slider_{chosen}")
            price = st.number_input("Price (DKK)", min_value=0, value=45, key=f"p_input_{chosen}")
            if st.button("Submit Rating", use_container_width=True):
                row = [chosen, f_name, "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", score, price]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("Save to Wishlist ❤️", use_container_width=True):
                row = [chosen, "Wishlist", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, 0]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        if name == best_value_bakery: 
            color, icon, prefix = "orange", "money", "glyphicon"
        elif name in top_3:
            rank = top_3.index(name); color = ["beige", "lightgray", "darkred"][rank]; icon, prefix = "star", "glyphicon"
        elif max_r >= 1.0: 
            color, icon, prefix = "green", "cutlery", "glyphicon"
        elif 0.01 < max_r < 1.0: 
            color, icon, prefix = "red", "heart", "glyphicon"
        else: 
            color, icon, prefix = "blue", "info-sign", "glyphicon"
            
        folium.Marker([row['lat'], row['lon']], tooltip=name, 
                       icon=folium.Icon(color=color, icon=icon, prefix=prefix)).add_to(m)
    
    m_data = st_folium(m, width=1100, height=500, key="main_map")
    if m_data and m_data.get("last_object_clicked_tooltip"):
        clicked = m_data["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Progress Checklist")
    check_list = [{"Bakery": n, "Status": ("✅ Tried" if bakery_max_rating.get(n,0) >= 1.0 else "❤️ Wishlist" if 0.01 < bakery_max_rating.get(n,0) < 1.0 else "⭕ To Visit"), "Times Rated": int(stats.loc[n, 'Rating_Count']) if n in stats.index else 0} for n in sorted(display_df['Bakery Name'].unique())]
    st.dataframe(pd.DataFrame(check_list), use_container_width=True, hide_index=True)

with t3:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏆 Top Rated")
        st.dataframe(stats[['Avg_Rating', 'Rating_Count']].sort_values('Avg_Rating', ascending=False).rename(columns={"Avg_Rating": "Rating", "Rating_Count": "Total Reviews"}))
    with c2:
        st.subheader("💰 Best Value")
        if best_value_bakery:
            st.metric(best_value_bakery, f"{stats.loc[best_value_bakery, 'Avg_Rating']:.2f} Stars", 
                      delta=f"DKK {stats.loc[best_value_bakery, 'Avg_Price']:.0f} avg price")
        
