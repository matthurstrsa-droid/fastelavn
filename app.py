import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time

# --- 1. CONNECTION ---
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

@st.cache_data(ttl=10)
def load_bakery_df():
    ws = get_worksheet()
    df = pd.DataFrame(ws.get_all_records())
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    # Ensure Price column exists, default to 0 if missing
    if 'Price' not in df.columns: df['Price'] = 0
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. FILTERS (Sidebar Expander) ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    with st.expander("🔍 Filters & Search", expanded=True):
        # Price Filter (Assuming DKK 0 to 100 range)
        max_p = int(df_clean['Price'].max()) if not df_clean.empty else 100
        price_range = st.slider("Price Range (DKK)", 0, max(100, max_p), (0, max(100, max_p)))
        
        # Rating Filter (1 to 5)
        min_rating = st.slider("Min Average Rating", 1.0, 5.0, 1.0, step=0.25)
    
    # Apply Filtering
    mask = (df_clean['Price'] >= price_range[0]) & (df_clean['Price'] <= price_range[1])
    filtered_df = df_clean[mask]
    
    # Calculate Averages for the filter
    avg_ratings = filtered_df[filtered_df['Rating'] >= 1.0].groupby('Bakery Name')['Rating'].mean()
    qualified_bakeries = avg_ratings[avg_ratings >= min_rating].index.tolist()
    
    # Final display list (includes wishlists regardless of rating filter)
    wishlist_bakeries = filtered_df[(filtered_df['Rating'] > 0) & (filtered_df['Rating'] < 1.0)]['Bakery Name'].unique().tolist()
    visible_bakeries = list(set(qualified_bakeries + wishlist_bakeries))
    
    display_df = filtered_df[filtered_df['Bakery Name'].isin(visible_bakeries)]

    st.divider()
    
    # --- ACTIONS (Add/Rate) ---
    if st.checkbox("➕ Add New Bakery"):
        with st.form("add_form"):
            n_name = st.text_input("Bakery Name")
            n_addr = st.text_input("Address")
            if st.form_submit_button("Save"):
                loc = Nominatim(user_agent="bakery_app").geocode(n_addr)
                if loc:
                    get_worksheet().append_row([n_name, "Base", "", n_addr, loc.latitude, loc.longitude, "", "Other", "User", 0.0, 0], value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.rerun()

    # SELECT & UPDATE
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_names:
        idx = all_names.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in all_names else 0
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen
        
        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        current_stat = b_rows['Rating'].max()
        is_wish = (0.01 < current_stat < 1.0)

        action = st.radio("Goal:", ["Rate it", "Wishlist"], index=1 if is_wish else 0)

        if action == "Rate it":
            score = st.slider("Your Rating", 1.0, 5.0, 4.0, step=0.25)
            price = st.number_input("Price (DKK)", min_value=0, value=45)
            if st.button("Submit Review"):
                row = [chosen, "New Flavor", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", score, price]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("Add/Update Wishlist ❤️"):
                row = [chosen, "Wishlist", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, 0]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- 3. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

# Rankings for Podium
rankings = df_clean[df_clean['Rating'] >= 1.0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False)
top_3 = rankings.head(3).index.tolist()

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    # Only show filtered bakeries on map
    status_map = display_df.groupby('Bakery Name')['Rating'].max().to_dict()
    
    for name, rating in status_map.items():
        coords = display_df[display_df['Bakery Name'] == name].iloc[0]
        if name in top_3:
            rank = top_3.index(name)
            color = ["orange", "lightgray", "darkred"][rank]
            icon = "star"
        elif rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < rating < 1.0: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        
        folium.Marker([coords['lat'], coords['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        clicked = m_out["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Checklist")
    check_data = []
    for n in visible_bakeries:
        r = status_map.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 1.0 else "⭕ To Visit"
        check_data.append({"Status": s, "Bakery": n})
    st.dataframe(pd.DataFrame(check_data), use_container_width=True, hide_index=True)

with t3:
    st.subheader("Leaderboard (1.0 - 5.0)")
    if not rankings.empty:
        st.dataframe(rankings.reset_index().style.format({"Rating": "{:.2f}"}), use_container_width=True)
