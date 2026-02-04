import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

# --- 1. CONFIG & DATA ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")
geolocator = Nominatim(user_agent="bakery_explorer_v16")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_resource
def get_worksheet():
    creds_info = st.secrets["connections"]["my_bakery_db"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    return sh.get_worksheet(0)

@st.cache_data(ttl=5)
def load_data():
    ws = get_worksheet()
    df = pd.DataFrame(ws.get_all_records())
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df

df = load_data()
worksheet = get_worksheet()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 2. LOGIC: RANKINGS & STATUS ---
# Average rating per bakery (excluding wishlist/zeros)
rankings = df_clean[df_clean['Rating'] >= 1.0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False)
top_3 = rankings.head(3).index.tolist()

# Status dictionary for icons
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Bakery Actions")
    is_new = st.checkbox("➕ Add New Bakery")
    if is_new:
        with st.form("new_bakery"):
            n_name = st.text_input("Name")
            n_addr = st.text_input("Address")
            if st.form_submit_button("Add to Map"):
                loc = geolocator.geocode(n_addr)
                if loc:
                    worksheet.append_row([n_name, "Base", "", n_addr, loc.latitude, loc.longitude, "", "Other", "User", 0.0, ""], value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.rerun()

    st.divider()
    all_bakeries = sorted(df_clean['Bakery Name'].unique().tolist())
    target = st.session_state.selected_bakery
    idx = all_bakeries.index(target) if target in all_bakeries else 0
    chosen = st.selectbox("Current Selection", all_bakeries, index=idx)
    st.session_state.selected_bakery = chosen

    b_rows = df_clean[df_clean['Bakery Name'] == chosen]
    is_wish = (0.01 < bakery_status.get(chosen, 0) < 0.2)

    if is_wish and st.button("❌ Remove from Wishlist", use_container_width=True):
        all_vals = worksheet.get_all_values()
        for i, row in enumerate(all_vals):
            if row[0] == chosen and (0.01 < float(row[9] or 0) < 0.2):
                worksheet.delete_rows(i + 1); break
        st.cache_data.clear(); st.rerun()

    mode = st.radio("Action:", ["Rate it", "Add to Wishlist"], index=1 if is_wish else 0, key=f"m_{chosen}")
    if mode == "Rate it":
        score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
        if st.button("Submit Rating ✅"):
            b_data = b_rows.iloc[0]
            worksheet.append_row([str(chosen), "New Flavor", "", str(b_data['Address']), float(b_data['lat']), float(b_data['lon']), "", "Other", "User", float(score), ""], value_input_option='USER_ENTERED')
            st.cache_data.clear(); st.rerun()
    elif st.button("Confirm Wishlist ❤️"):
        b_data = b_rows.iloc[0]
        worksheet.append_row([str(chosen), "Wishlist", "", str(b_data['Address']), float(b_data['lat']), float(b_data['lon']), "", "Other", "User", 0.1, ""], value_input_option='USER_ENTERED')
        st.cache_data.clear(); st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map View", "📝 Interactive Checklist", "🏆 Leaderboard"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        
        # PODIUM LOGIC
        if name in top_3:
            rank = top_3.index(name)
            colors = ["orange", "lightgray", "darkred"] # Gold, Silver, Bronze
            icons = ["star", "star", "star"]
            color = colors[rank]
            icon = icons[rank]
        elif rating >= 1.0: 
            color, icon = "green", "cutlery"
        elif 0.01 < rating < 0.2: 
            color, icon = "red", "heart"
        else: 
            color, icon = "blue", "info-sign"
            
        folium.Marker([coords['lat'], coords['lon']], tooltip=name, 
                       icon=folium.Icon(color=color, icon=icon, prefix='fa', icon_color='white')).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        clicked = m_out["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Edit Status")
    list_items = []
    for n in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 0.2 else "⭕ To Visit"
        list_items.append({"Status": s, "Bakery": n})
    
    edited_df = st.data_editor(pd.DataFrame(list_items), key="list_edit", use_container_width=True, hide_index=True,
                               column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])})
    
    # Quick-save for wishlist changes in table
    for i, row in edited_df.iterrows():
        if row['Status'] != list_items[i]['Status']:
            target = row['Bakery']
            if row['Status'] == "❤️ Wishlist":
                b_data = df_clean[df_clean['Bakery Name'] == target].iloc[0]
                worksheet.append_row([target, "Wishlist", "", b_data['Address'], b_data['lat'], b_data['lon'], "", "Other", "User", 0.1, ""], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
            elif row['Status'] == "✅ Tried":
                st.session_state.selected_bakery = target
                st.rerun()

with t3:
    st.subheader("🏆 The Top Rated Bakeries")
    if not rankings.empty:
        # Display with medal emojis
        ranked_df = rankings.reset_index()
        ranked_df.columns = ['Bakery', 'Average Rating']
        ranked_df.index = ranked_df.index + 1
        st.dataframe(ranked_df.style.highlight_max(axis=0, color='gold'), use_container_width=True)
