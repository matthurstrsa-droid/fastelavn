import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

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

@st.cache_data(ttl=5)
def load_bakery_df():
    ws = get_worksheet()
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    # Force columns to exist and be numeric
    numeric_cols = ['Rating', 'Price', 'lat', 'lon']
    for col in numeric_cols:
        if col not in df.columns: df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    if 'Fastelavnsbolle Type' not in df.columns: df['Fastelavnsbolle Type'] = ""
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. CALCULATE SPECIAL STATUSES ---
# Average Rating & Best Value
stats = df_clean[df_clean['Rating'] >= 1.0].groupby('Bakery Name').agg({
    'Rating': 'mean',
    'Price': 'mean'
})

# Best Value = Max (Rating / Price) -> excluding 0 price to avoid infinity
stats['Value_Score'] = stats.apply(lambda x: x['Rating'] / x['Price'] if x['Price'] > 0 else 0, axis=1)
best_value_bakery = stats['Value_Score'].idxmax() if not stats.empty else None

# Podium
rankings = stats['Rating'].sort_values(ascending=False)
top_3 = rankings.head(3).index.tolist()

# Current Status for Icons
bakery_status = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR FILTERS ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    with st.expander("🔍 Filter View", expanded=True):
        # Price Filter
        max_p_data = int(df_clean['Price'].max()) if not df_clean.empty else 100
        price_range = st.slider("Price (DKK)", 0, max(100, max_p_data), (0, max(100, max_p_data)))
        
        # Rating Filter
        min_r = st.slider("Min Rating", 1.0, 5.0, 1.0, step=0.25)

    # Apply Filters to the dataframe used for Map/List
    mask = (df_clean['Price'] >= price_range[0]) & (df_clean['Price'] <= price_range[1])
    # Keep bakeries that meet rating OR are wishlisted (0.1)
    filtered_names = stats[stats['Rating'] >= min_r].index.tolist()
    wishlist_names = df_clean[(df_clean['Rating'] > 0) & (df_clean['Rating'] < 1.0)]['Bakery Name'].tolist()
    
    display_df = df_clean[mask & (df_clean['Bakery Name'].isin(filtered_names + wishlist_names))]

    st.divider()
    
    # --- ACTIONS ---
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_names:
        idx = all_names.index(st.session_state.selected_bakery) if st.session_state.selected_bakery in all_names else 0
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen
        
        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        
        # RESTORE FLAVORS dropdown
        existing_flavs = sorted([str(f) for f in b_rows['Fastelavnsbolle Type'].unique() if f and str(f).strip()])
        f_sel = st.selectbox("Flavor", existing_flavs + ["➕ New..."], key=f"f_{chosen}")
        f_name = st.text_input("New flavor name:") if f_sel == "➕ New..." else f_sel

        action = st.radio("Goal:", ["Rate it", "Wishlist"], index=0)

        if action == "Rate it":
            score = st.slider("Rating", 1.0, 5.0, 4.0, step=0.25)
            price = st.number_input("Price (DKK)", min_value=0, value=45)
            if st.button("Submit Review"):
                row = [chosen, f_name, "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", score, price]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()
        else:
            if st.button("Add to Wishlist ❤️"):
                row = [chosen, "Wishlist", "", b_rows.iloc[0].get('Address', ''), b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, 0]
                get_worksheet().append_row(row, value_input_option='USER_ENTERED')
                st.cache_data.clear(); st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13)
    
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        rating = bakery_status.get(name, 0)
        
        # ICON LOGIC
        if name == best_value_bakery:
            color, icon = "orange", "certificate" # "Best Value" Icon
        elif name in top_3:
            rank = top_3.index(name)
            color = ["beige", "lightgray", "darkred"][rank] # Gold/Silver/Bronze
            icon = "star"
        elif rating >= 1.0: 
            color, icon = "green", "cutlery"
        elif 0.01 < rating < 1.0: 
            color, icon = "red", "heart"
        else: 
            color, icon = "blue", "info-sign"
            
        folium.Marker([row['lat'], row['lon']], tooltip=f"{name} (Value Rank!)" if name == best_value_bakery else name, 
                       icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    m_out = st_folium(m, width=1100, height=500, key="main_map")
    if m_out and m_out.get("last_object_clicked_tooltip"):
        st.session_state.selected_bakery = m_out["last_object_clicked_tooltip"]
        st.rerun()

with t2:
    st.subheader("Progress Checklist")
    # Show bakeries matching the filter
    check_list = []
    for n in sorted(display_df['Bakery Name'].unique()):
        r = bakery_status.get(n, 0)
        s = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 1.0 else "⭕ To Visit"
        check_list.append({"Status": s, "Bakery": n})
    st.dataframe(pd.DataFrame(check_list), use_container_width=True, hide_index=True)

with t3:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏆 Top Rated")
        st.dataframe(rankings.reset_index().rename(columns={"Rating": "Avg Rating"}))
    with col2:
        st.subheader("💎 Best Value")
        if best_value_bakery:
            st.metric(best_value_bakery, f"{stats.loc[best_value_bakery, 'Rating']:.2f} Stars", 
                      delta=f"DKK {stats.loc[best_value_bakery, 'Price']:.0f}")
