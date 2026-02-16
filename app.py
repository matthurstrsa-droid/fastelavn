import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import numpy as np
import cloudinary.uploader

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

# Initialize Session States
defaults = {
    "arrival_times": {}, 
    "selected_bakery": None, 
    "merchant_bakery": None, 
    "user_nickname": "BunHunter",
    "review_mode": None,
    "user_filter": None 
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 2. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)

@st.cache_data(ttl=2)
def load_data():
    try:
        data = get_worksheet().get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return df
        df.columns = [c.strip() for c in df.columns]
        
        expected = ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time', 'Photo URL', 'Comment']
        for col in expected:
            if col not in df.columns:
                df[col] = 0 if col not in ['Photo URL', 'Comment'] else ""
            elif col in ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Sync Error: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 3. SANITIZED DATA UPDATE ---
def post_to_sheets(row_list):
    sanitized = []
    for item in row_list:
        if isinstance(item, (np.int64, np.int32)): sanitized.append(int(item))
        elif isinstance(item, (np.float64, np.float32)): sanitized.append(float(item))
        elif pd.isna(item): sanitized.append("")
        else: sanitized.append(str(item))
    get_worksheet().append_row(sanitized, value_input_option='USER_ENTERED')

# --- 4. TABS ---
t_map, t_stream, t_top, t_settings, t_help = st.tabs(["📍 Map", "🧵 Stream", "🏆 Leaderboard", "⚙️ Settings", "❓ Help"])

with t_map:
    # --- SEARCH ---
    search_q = st.text_input("🔍 Search (vegan, mocha, bakery name...)", "").lower().strip()
    filtered = df_raw.copy()
    if search_q and not filtered.empty:
        corpus = (filtered['Bakery Name'].astype(str) + " " + filtered['Fastelavnsbolle Type'].astype(str)).str.lower()
        filtered = filtered[corpus.str.contains(search_q, na=False)]

    # --- ACTION CENTER ---
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_data = df_raw[df_raw['Bakery Name'] == name].iloc[0]
        is_merchant = st.session_state.merchant_bakery == name
        
        with st.expander(f"📍 {name} {'(ADMIN MODE)' if is_merchant else ''}", expanded=True):
            
            # --- MERCHANT ADMIN VIEW ---
            if is_merchant:
                st.subheader("🧑‍🍳 Update Your Shop")
                with st.form("merchant_update"):
                    new_stock = st.number_input("Current Stock Count", 0, 1000, int(b_data['Stock']))
                    new_flavor = st.text_input("Today's Featured Flavor", value=str(b_data['Fastelavnsbolle Type']))
                    new_price = st.number_input("Price (DKK)", 0, 200, int(b_data['Price']))
                    m_comm = st.text_area("Merchant Note (e.g., 'Next batch at 2pm!')", value="Freshly restocked!")
                    
                    if st.form_submit_button("Broadcast Update"):
                        row = [name, new_flavor, "", str(b_data['Address']), float(b_data['lat']), float(b_data['lon']),
                               get_now_dk().strftime("%Y-%m-%d"), "Merchant", name, 5.0, 
                               new_price, new_stock, get_now_dk().strftime("%H:%M"), "", m_comm, 0]
                        post_to_sheets(row)
                        st.cache_data.clear(); st.success("Broadcast sent!"); st.rerun()

            # --- USER VIEW ---
            else:
                # 🚨 STOCK OUT ANNOUNCEMENT
                if b_data['Stock'] <= 0:
                    st.error(f"### 🚫 SOLD OUT AT {name.upper()}")
                    st.info(f"Last reported flavor: {b_data['Fastelavnsbolle Type']}")
                    if st.button("Close"): st.session_state.selected_bakery = None; st.rerun()
                
                else:
                    # Choice: Timer or Instant
                    if name not in st.session_state.arrival_times and st.session_state.review_mode != "instant":
                        st.success(f"✅ In Stock: {int(b_data['Stock'])} available")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("🏁 Join Line"):
                                st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}; st.rerun()
                        with col2:
                            if st.button("🚀 Fast Review"):
                                st.session_state.review_mode = "instant"; st.rerun()
                    
                    # Review Form Path
                    else:
                        wait_val = 0
                        show_form = False
                        if st.session_state.review_mode == "instant":
                            show_form = True
                        elif name in st.session_state.arrival_times:
                            if st.session_state.arrival_times[name]["wait"] is None:
                                w_now = (get_now_dk() - st.session_state.arrival_times[name]["start"]).seconds // 60
                                st.info(f"⏱️ Waiting: {w_now} mins...")
                                if st.button("🛍️ Got it!", type="primary"):
                                    st.session_state.arrival_times[name]["wait"] = max(1, w_now); st.rerun()
                            else:
                                show_form = True
                                wait_val = st.session_state.arrival_times[name]["wait"]

                        if show_form:
                            with st.form("final_review"):
                                uploaded_file = st.file_uploader("📸 Photo", type=['jpg', 'jpeg', 'png'])
                                t_f = st.text_input("Flavor", value=str(b_data['Fastelavnsbolle Type']))
                                t_r = st.slider("Rating", 1.0, 5.0, 4.0, 0.5)
                                t_c = st.text_area("Review")
                                if st.form_submit_button("Submit"):
                                    photo_url = ""
                                    if uploaded_file: photo_url = cloudinary.uploader.upload(uploaded_file)['secure_url']
                                    row = [name, t_f, photo_url, str(b_data['Address']), float(b_data['lat']), float(b_data['lon']),
                                           get_now_dk().strftime("%Y-%m-%d"), "User", str(st.session_state.user_nickname),
                                           float(t_r), float(b_data['Price']), int(b_data['Stock']), get_now_dk().strftime("%H:%M"),
                                           "", str(t_c), int(wait_val)]
                                    post_to_sheets(row)
                                    if name in st.session_state.arrival_times: del st.session_state.arrival_times[name]
                                    st.session_state.review_mode = None; st.session_state.selected_bakery = None
                                    st.cache_data.clear(); st.balloons(); st.rerun()

            if st.button("Cancel"):
                if name in st.session_state.arrival_times: del st.session_state.arrival_times[name]
                st.session_state.review_mode = None; st.session_state.selected_bakery = None; st.rerun()

    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")
    for _, r in filtered.dropna(subset=['lat', 'lon']).iterrows():
        color = "red" if r['Stock'] <= 0 else "green"
        folium.Marker([r['lat'], r['lon']], tooltip=r['Bakery Name'], icon=folium.Icon(color=color)).add_to(m)
    res = st_folium(m, width="100%", height=500, key="main_map")
    if res.get("last_object_clicked_tooltip"):
        clicked = res["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked; st.rerun()

with t_stream:
    if st.session_state.user_filter:
        st.info(f"Showing posts by: @{st.session_state.user_filter}")
        if st.button("Clear Filter"): st.session_state.user_filter = None; st.rerun()

    if not df_raw.empty:
        s_df = df_raw.sort_values(by=["Date", "Time"], ascending=False)
        if st.session_state.user_filter: s_df = s_df[s_df['User'] == st.session_state.user_filter]
        
        for _, r in s_df.iterrows():
            with st.container(border=True):
                role = "🧑‍🍳 MERCHANT" if r['Category'] == 'Merchant' else f"👤 @{r['User']}"
                st.write(f"**{r['Bakery Name']}** | {role}")
                if r['Photo URL']: st.image(r['Photo URL'], width=400)
                st.write(f"⭐ {r['Rating']} | ⏳ {int(r.get('Wait Time', 0))}m wait | 🍩 {r['Fastelavnsbolle Type']}")
                if r['Comment']: st.info(r['Comment'])

with t_top:
    st.header("🏆 Rankings")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🥇 Bakeries")
        st.dataframe(df_raw[df_raw['Rating'] > 0].groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False), use_container_width=True)
        st.subheader("🍦 Flavors")
        st.dataframe(df_raw[df_raw['Rating'] > 0].groupby(['Fastelavnsbolle Type', 'Bakery Name'])['Rating'].mean().sort_values(ascending=False), use_container_width=True)
    with c2:
        st.subheader("👑 Top Hunters")
        u_counts = df_raw[df_raw['Category'] == 'User']['User'].value_counts().reset_index()
        for i, row in u_counts.iterrows():
            col_a, col_b = st.columns([3,1])
            col_a.write(f"@{row['User']} ({row['count']} reviews)")
            if col_b.button("View", key=f"u_{i}"):
                st.session_state.user_filter = row['User']; st.rerun()

with t_settings:
    st.subheader("⚙️ Settings")
    st.session_state.user_nickname = st.text_input("Nickname", st.session_state.user_nickname)
    st.divider()
    if st.session_state.merchant_bakery:
        st.success(f"Merchant Access: {st.session_state.merchant_bakery}")
        if st.button("Log Out"): st.session_state.merchant_bakery = None; st.rerun()
    else:
        k_in = st.text_input("Bakery Secret Key", type="password")
        if st.button("Unlock Merchant Map Tools"):
            match = df_raw[df_raw['Bakery Key'].astype(str) == k_in]
            if not match.empty:
                st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]; st.rerun()

with t_help:
    st.markdown("### 🥐 Tips\n- Pins turn **Red** on the map when stock is 0.\n- Use **Fast Review** if you've already eaten!")
