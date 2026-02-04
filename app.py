import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time

# --- 1. THE CONNECTION (Bulletproofed) ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

# Persistent connection to GSheets
if "gs_client" not in st.session_state:
    try:
        creds_info = st.secrets["connections"]["my_bakery_db"]
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        st.session_state.gs_client = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Authentication Failed: {e}")
        st.stop()

def get_worksheet():
    sh = st.session_state.gs_client.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    return sh.get_worksheet(0)

# --- 2. DATA LOADING ---
@st.cache_data(ttl=10) # 10 seconds cache to reduce API hits
def load_bakery_df():
    ws = get_worksheet()
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    # Standardize types
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 3. RANKINGS & STATUS ---
rankings = df_clean[df_clean['Rating'] >= 1.0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False)
top_3 = rankings.head(3).index.tolist()
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 4. SIDEBAR ---
if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

with st.sidebar:
    st.header("🥯 Control Panel")
    
    # ADD NEW
    if st.checkbox("➕ Add New Bakery"):
        with st.form("add_form"):
            n_name = st.text_input("Bakery Name")
            n_addr = st.text_input("Address")
            if st.form_submit_button("Save to DB"):
                loc = Nominatim(user_agent="bakery_app").geocode(n_addr)
                if loc:
                    get_worksheet().append_row([n_name, "Base", "", n_addr, loc.latitude, loc.longitude, "", "Other", "User", 0.0, ""], value_input_option='USER_ENTERED')
                    st.cache_data.clear()
                    st.success("Added! Refreshing..."); time.sleep(1); st.rerun()

    st.divider()

    # SELECT EXISTING
    all_names = sorted(df_clean['Bakery Name'].unique().tolist()) if not df_clean.empty else []
    if all_names:
        idx = all_names.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in all_names else 0
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen

        # Action Logic
        current_r = bakery_status.get(chosen, 0)
        is_wish = (0.01 < current_r < 0.2)
        
        # Display flavor options if they exist
        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        flavors = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f and str(f).strip()])
        f_sel = st.selectbox("Flavor", flavors + ["➕ New..."], key=f"f_{chosen}")
        f_name = st.text_input("New flavor name:") if f_sel == "➕ New..." else f_sel

        action = st.radio("Goal:", ["Rate it", "Wishlist"], index=1 if is_wish else 0)

        if action == "Rate it":
            score = st.slider("Rating", 1.0, 10.0, 8.0, step=0.5)
            if st.button("Submit Review"):
                row = [chosen, f_name, "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", score, ""]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
        else:
            if not is_wish:
                if st.button("Add to Wishlist ❤️"):
                    row = [chosen, "Wishlist", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, ""]
                    get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.rerun()
            else:
                if st.button("❌ Remove from Wishlist"):
                    ws = get_worksheet()
                    cells = ws.findall(chosen)
                    for cell in cells:
                        if 0.01 < float(ws.cell(cell.row, 10).value or 0) < 0.2:
                            ws.delete_rows(cell.row); break
                    st.cache_data.clear(); st.rerun()

# --- 5. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    for name, rating in bakery_status.items():
        coords = df_clean[df_clean['Bakery Name'] == name].iloc[0]
        if name in top_3:
            rank = top_3.index(name)
            color = ["orange", "lightgray", "darkred"][rank] # Gold/Silver/Bronze
            icon = "star"
        elif rating >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < rating < 0.2: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        folium.Marker([coords['lat'], coords['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        clicked = m_out["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Interactive Checklist")
    # Generate static list for comparison
    base_data = []
    for n in sorted(df_clean['Bakery Name'].unique()):
        r = bakery_status.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 0.2 else "⭕ To Visit"
        base_data.append({"Status": s, "Bakery": n})
    
    edited = st.data_editor(pd.DataFrame(base_data), hide_index=True, use_container_width=True,
                            column_config={"Status": st.column_config.SelectboxColumn("Status", options=["✅ Tried", "❤️ Wishlist", "⭕ To Visit"])})
    
    # Instant Wishlist Save
    for i, row in edited.iterrows():
        if row['Status'] != base_data[i]['Status']:
            if row['Status'] == "❤️ Wishlist":
                b_info = df_clean[df_clean['Bakery Name'] == row['Bakery']].iloc[0]
                get_worksheet().append_row([row['Bakery'], "Wishlist", "", b_info['Address'], b_info['lat'], b_info['lon'], "", "Other", "User", 0.1, ""], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
            elif row['Status'] == "✅ Tried":
                st.session_state.selected_bakery = row['Bakery']
                st.rerun()

with t3:
    st.subheader("Leaderboard")
    if not rankings.empty:
        st.dataframe(rankings.reset_index().rename(columns={"Rating": "Avg Rating"}), use_container_width=True)
