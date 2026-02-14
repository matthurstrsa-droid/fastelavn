import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from datetime import datetime
import pytz
import cloudinary.uploader
import time

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="BolleQuest Pro", layout="wide", initial_sidebar_state="collapsed")

def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen')).strftime("%H:%M")

# Initialize Session States
for key, val in {"selected_bakery": None, "is_merchant": False}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 2. DATA CONNECTION ---
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def get_worksheet():
    try:
        return get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo").get_worksheet(0)
    except Exception:
        st.error("⚠️ Access Denied. Please share your Google Sheet with the Service Account email in your secrets.")
        st.stop()

@st.cache_data(ttl=5)
def load_data():
    df = pd.DataFrame(get_worksheet().get_all_records())
    df.columns = [c.strip() for c in df.columns]
    # Critical Type Casting
    for col in ['lat', 'lon', 'Rating', 'Price', 'Stock']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df = load_data()
df_clean = df.dropna(subset=['lat', 'lon'])

# --- 3. GLOBAL SEARCH & FILTER ---
st.title("🥯 BolleQuest")
search_q = st.text_input("🔍 Search flavor, bakery, or area...", placeholder="e.g. 'Pistachio' or 'Hart'").strip().lower()

filtered = df_clean.copy()
if search_q:
    mask = (
        filtered['Fastelavnsbolle Type'].str.lower().str.contains(search_q, na=False) | 
        filtered['Bakery Name'].str.lower().str.contains(search_q, na=False)
    )
    filtered = filtered[mask]

# --- 4. ACTION CENTER (Popover Logic) ---
if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_rows = df_clean[df_clean['Bakery Name'] == name]
    if not b_rows.empty:
        row = b_rows.iloc[0]
        with st.popover(f"📍 {name}", use_container_width=True):
            stock = int(b_rows['Stock'].max())
            l_upd = row.get('Last Updated', '--:--')
            
            c1, c2 = st.columns(2)
            c1.metric("Stock", "SOLD OUT" if stock <= 0 else f"{stock} left")
            c2.metric("Updated", l_upd)
            
            st.link_button("🚗 Directions", f"https://www.google.com/maps/dir/?api=1&destination={row['lat']},{row['lon']}", use_container_width=True)
            
            if st.button("🚨 Report SOLD OUT", use_container_width=True):
                ws = get_worksheet()
                cell = ws.find(name)
                ws.update_cell(cell.row, 12, 0)
                ws.update_cell(cell.row, 13, get_now_dk())
                st.toast("Community updated! 🥐")
                st.cache_data.clear(); time.sleep(1); st.rerun()

            st.divider()
            # MERCHANT DASHBOARD
            if st.session_state.is_merchant:
                new_s = st.number_input("Merchant: Restock count", 0, 500, 50)
                if st.button("Update Inventory"):
                    ws = get_worksheet()
                    cell = ws.find(name)
                    ws.update_cell(cell.row, 12, new_s)
                    ws.update_cell(cell.row, 13, get_now_dk())
                    st.cache_data.clear(); st.rerun()
            
            if st.button("Close Window ✕", use_container_width=True):
                st.session_state.selected_bakery = None; st.rerun()

# --- 5. MOBILE TABS ---
t_map, t_buns, t_gallery, t_route, t_top, t_app = st.tabs(["📍 Map", "📜 Buns", "📸 Gallery", "🚲 Route", "🏆 Top", "📲 App"])

with t_map:
    # Handle empty map states
    center = [55.6761, 12.5683]
    m = folium.Map(location=center, zoom_start=13, tiles="cartodbpositron")
    
    for _, r in filtered.iterrows():
        color = "red" if r['Stock'] <= 0 else "darkblue" if r['Bakery Name'] == st.session_state.selected_bakery else "green"
        folium.Marker(
            [r['lat'], r['lon']], 
            tooltip=r['Bakery Name'], 
            icon=folium.Icon(color=color, icon="shopping-basket", prefix="fa")
        ).add_to(m)
    
    map_res = st_folium(m, width="100%", height=450, key="main_map")
    if map_res and map_res.get("last_object_clicked_tooltip"):
        st.session_state.selected_bakery = map_res["last_object_clicked_tooltip"]
        st.rerun()

with t_buns:
    st.subheader("Latest Check-ins")
    rated = filtered[filtered['Rating'] > 0].sort_values('Rating', ascending=False)
    for i, r in enumerate(rated.itertuples()):
        # Unique key prevents DuplicateElementId error
        if st.button(f"⭐ {r.Rating} | {r._2} @ {r._1}", key=f"feed_{i}", use_container_width=True):
            st.session_state.selected_bakery = r._1; st.rerun()

with t_gallery:
    photos = filtered[filtered['Photo URL'].str.contains("http", na=False)]
    cols = st.columns(2)
    for i, r in enumerate(photos.tail(20).iloc[::-1].itertuples()):
        with cols[i % 2]:
            st.image(r._3, use_container_width=True)
            st.caption(f"{r._2} @ {r._1}")

with t_route:
    st.subheader("🚲 Efficient Bun Route")
    # Finds 5 closest bakeries that ARE in stock
    stock_df = filtered[filtered['Stock'] > 0].copy()
    if not stock_df.empty:
        stock_df['dist'] = stock_df.apply(lambda r: geodesic((55.6761, 12.5683), (r['lat'], r['lon'])).km, axis=1)
        route = stock_df.sort_values('dist').head(5)
        for i, r in enumerate(route.itertuples()):
            if st.button(f"{i+1}. {r._1} ({r.dist:.1f}km)", key=f"rt_{i}", use_container_width=True):
                st.session_state.selected_bakery = r._1; st.rerun()
    else:
        st.warning("No bakeries currently in stock in this search area.")

with t_top:
    st.header("🏆 Rankings")
    c1, c2, c3 = st.columns(3)
    rd = df_clean[df_clean['Rating'] > 0]
    if not rd.empty:
        with c1:
            st.write("**Top Flavors**")
            st.dataframe(rd.groupby('Fastelavnsbolle Type')['Rating'].mean().sort_values(ascending=False).head(5), hide_index=False)
        with c2:
            st.write("**Top Bakeries**")
            st.dataframe(rd.groupby('Bakery Name')['Rating'].mean().sort_values(ascending=False).head(5), hide_index=False)
        with c3:
            st.write("**Top Users**")
            st.dataframe(rd['User'].value_counts().head(5), hide_index=False)

with t_app:
    st.subheader("📲 Install BolleQuest")
    st.write("**iPhone:** Share > Add to Home Screen")
    st.write("**Android:** ⋮ Menu > Install App")
    st.divider()
    st.header("🧑‍🍳 Merchant Login")
    if st.text_input("Bakery Key", type="password") == st.secrets.get("general", {}).get("bakery_key", ""):
        st.session_state.is_merchant = True
        st.success("Merchant Mode On")
