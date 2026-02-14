import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from folium.plugins import Geocoder
from geopy.geocoders import Nominatim
import cloudinary
import cloudinary.uploader

# --- 1. SETUP & CLOUDINARY CONFIG ---
st.set_page_config(page_title="Bakery Tracker Pro", layout="wide")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

# Configure Cloudinary from Secrets
try:
    cloudinary.config(
        cloud_name = st.secrets["cloudinary"]["cloud_name"],
        api_key = st.secrets["cloudinary"]["api_key"],
        api_secret = st.secrets["cloudinary"]["api_secret"],
        secure = True
    )
except Exception as e:
    st.warning("📸 Photo uploads disabled: Check Cloudinary secrets.")

# Auth & Data Connection
try:
    if "gs_client" not in st.session_state:
        creds_info = st.secrets["connections"]["my_bakery_db"]
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        st.session_state.gs_client = gspread.authorize(creds)
except Exception as e:
    st.error("🔒 Security Handshake Failed.")
    st.stop()

def get_worksheet():
    sh = st.session_state.gs_client.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    return sh.get_worksheet(0)

@st.cache_data(ttl=2)
def load_bakery_df():
    try:
        ws = get_worksheet()
        df = pd.DataFrame(ws.get_all_records())
        df.columns = [c.strip() for c in df.columns]
        for col in ['Rating', 'Price', 'lat', 'lon']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df
    except:
        return pd.DataFrame()

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. STATS LOGIC ---
rated_only = df_clean[df_clean['Rating'] >= 1.0] if not df_clean.empty else pd.DataFrame()
stats = pd.DataFrame()
best_value_bakery, top_3 = None, []

if not rated_only.empty:
    stats = rated_only.groupby('Bakery Name').agg({'Rating': ['mean', 'count'], 'Price': 'mean'})
    stats.columns = ['Avg_Rating', 'Rating_Count', 'Avg_Price']
    val_stats = stats[stats['Avg_Price'] > 0].copy()
    if not val_stats.empty:
        val_stats['Val'] = val_stats['Avg_Rating'] / val_stats['Avg_Price']
        best_value_bakery = val_stats['Val'].idxmax()
    top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Control Panel")
    with st.expander("🆕 Add New Bakery"):
        new_name = st.text_input("Bakery Name")
        new_addr = st.text_input("Address (Copenhagen)")
        if st.button("📍 Add to Sheet", use_container_width=True):
            if new_name and new_addr:
                loc = Nominatim(user_agent="bakery_explorer").geocode(new_addr)
                if loc:
                    # New Row: [Name, Flavor, Photo_URL, Addr, Lat, Lon, Date, Category, User, Rating, Price, Hours]
                    get_worksheet().append_row([new_name, "Wishlist", "", new_addr, loc.latitude, loc.longitude, "", "Other", "User", 0.1, 0, ""], value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.rerun()
    
    if not df_clean.empty:
        all_names = sorted(df_clean['Bakery Name'].unique().tolist())
        sel = st.session_state.selected_bakery
        chosen = st.selectbox("Select Bakery", all_names, index=all_names.index(sel) if sel in all_names else 0)
        st.session_state.selected_bakery = chosen

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")

# --- MOBILE ACTION CENTER (Popover) ---
if st.session_state.selected_bakery:
    chosen = st.session_state.selected_bakery
    b_rows = df_clean[df_clean['Bakery Name'] == chosen]
    row = b_rows.iloc[0]
    raw_flavs = b_rows['Fastelavnsbolle Type'].unique()
    
    with st.popover(f"✨ Actions for {chosen}", use_container_width=True):
        hours = row.get('Opening Hours', "Check Google")
        st.info(f"🕒 **Hours:** {hours}")
        
        lat, lon = row['lat'], row['lon']
        st.link_button("🚗 Directions", f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}", use_container_width=True)
        
        st.divider()
        on_wishlist = "Wishlist" in raw_flavs
        if on_wishlist:
            if st.button("❌ Remove Wishlist", use_container_width=True):
                ws = get_worksheet(); all_data = ws.get_all_records()
                for i, r_data in enumerate(all_data):
                    if r_data.get("Bakery Name") == chosen and r_data.get("Fastelavnsbolle Type") == "Wishlist":
                        ws.delete_rows(i + 2); break
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("❤️ Add Wishlist", use_container_width=True):
                get_worksheet().append_row([chosen, "Wishlist", "", row['Address'], lat, lon, "", "Other", "User", 0.1, 0, hours], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

        st.divider()
        st.markdown("**Rate & Photo**")
        flavs = sorted([str(f).strip() for f in raw_flavs if f and str(f).strip() and not str(f).isdigit() and str(f) != "Wishlist"])
        f_sel = st.selectbox("Flavor", flavs + ["➕ New..."], key="pop_f")
        if f_sel == "➕ New...":
            f_sel = st.text_input("Flavor Name", key="pop_new_f")
        
        r = st.slider("Rating", 1.0, 5.0, 4.0, 0.5)
        p = st.number_input("Price (DKK)", 0, 150, 45)
        
        # 📸 PHOTO UPLOAD FIELD
        img_file = st.file_uploader("Upload Bun Photo", type=['jpg', 'png', 'jpeg'])
        
        if st.button("Submit Review ✅", use_container_width=True):
            with st.spinner("Uploading photo & saving..."):
                photo_url = ""
                if img_file:
                    upload_result = cloudinary.uploader.upload(img_file)
                    photo_url = upload_result.get("secure_url")
                
                get_worksheet().append_row([chosen, f_sel, photo_url, row['Address'], lat, lon, "", "Other", "User", r, p, hours], value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- TABS ---
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    Geocoder().add_to(m)
    for name in df_clean['Bakery Name'].unique():
        b_data = df_clean[df_clean['Bakery Name'] == name]
        row_m = b_data.iloc[0]
        on_wishlist = "Wishlist" in b_data['Fastelavnsbolle Type'].values
        has_rating = any(b_data['Rating'] >= 1.0)
        
        # Priority: Selected > Best Value > Top 3 > Rated > Wishlist
        if name == st.session_state.selected_bakery: color, icon = "darkblue", "flag"
        elif name == best_value_bakery: color, icon = "orange", "usd"
        elif name in top_3: color, icon = "darkred", "star"
        elif has_rating: color, icon = "green", "cutlery"
        elif on_wishlist: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        
        folium.Marker([row_m['lat'], row_m['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    map_out = st_folium(m, width="100%", height=450, key="main_map")
    if map_out and map_out.get("last_object_clicked_tooltip"):
        clicked = map_out["last_object_clicked_tooltip"]
        if clicked != st.session_state.selected_bakery:
            st.session_state.selected_bakery = clicked; st.rerun()

with t2:
    st.subheader("Checklist & Gallery")
    # Display logic for rows that have photos
    df_photos = df_clean[df_clean['Photo URL'] != ""]
    if not df_photos.empty:
        st.markdown("### 📸 Recent Sightings")
        cols = st.columns(3)
        for idx, p_row in enumerate(df_photos.tail(6).iloc[::-1].itertuples()):
            with cols[idx % 3]:
                st.image(p_row._3, caption=f"{p_row._1}: {p_row._2}", use_container_width=True)

with t3:
    if not stats.empty:
        st.subheader("🏆 Leaderboard")
        st.dataframe(stats.sort_values('Avg_Rating', ascending=False), use_container_width=True)
