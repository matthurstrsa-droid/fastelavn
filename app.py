import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
import time

# --- 1. SETUP & CONNECTION ---
st.set_page_config(page_title="Bakery Tracker", layout="wide")

if "selected_bakery" not in st.session_state:
    st.session_state.selected_bakery = None

@st.cache_resource
def get_gs_worksheet():
    creds_info = st.secrets["connections"]["my_bakery_db"]
    creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    sh = client.open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    return sh.get_worksheet(0)

ws = get_gs_worksheet()

@st.cache_data(ttl=60)
def load_bakery_df():
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.strip() for c in df.columns]
    for col in ['Rating', 'Price', 'lat', 'lon']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

df = load_bakery_df()
df_clean = df.dropna(subset=['lat', 'lon']) if not df.empty else pd.DataFrame()

# --- 2. STATS LOGIC ---
rated_only = df_clean[df_clean['Rating'] >= 1.0]
stats = pd.DataFrame()
best_value_bakery = None
top_3 = []

if not rated_only.empty:
    stats = rated_only.groupby('Bakery Name').agg({'Rating': ['mean', 'count'], 'Price': 'mean'})
    stats.columns = ['Avg_Rating', 'Rating_Count', 'Avg_Price']
    val_stats = stats[stats['Avg_Price'] > 0].copy()
    if not val_stats.empty:
        val_stats['Val'] = val_stats['Avg_Rating'] / val_stats['Avg_Price']
        best_value_bakery = val_stats['Val'].idxmax()
    top_3 = stats['Avg_Rating'].sort_values(ascending=False).head(3).index.tolist()

bakery_max_rating = df_clean.groupby('Bakery Name')['Rating'].max().to_dict()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🥯 Control Panel")
    
    with st.expander("🔍 Map Filters", expanded=True):
        max_p = int(df_clean['Price'].max()) if not df_clean.empty else 100
        p_range = st.slider("Price (DKK)", 0, max(100, max_p), (0, max(100, max_p)))
        min_r = st.slider("Min Rating", 1.0, 5.0, 1.0, 0.25)

    def is_visible(name):
        if name == best_value_bakery: return True
        if name in stats.index:
            avg_r, avg_p = stats.loc[name, 'Avg_Rating'], stats.loc[name, 'Avg_Price']
            return (avg_r >= min_r) and ((p_range[0] <= avg_p <= p_range[1]) if avg_p > 0 else True)
        return True

    visible_names = [n for n in df_clean['Bakery Name'].unique() if is_visible(n)]
    display_df = df_clean[df_clean['Bakery Name'].isin(visible_names)]

    st.divider()
    all_names = sorted(df_clean['Bakery Name'].unique().tolist())
    if all_names:
        sel = st.session_state.selected_bakery
        idx = all_names.index(sel) if sel in all_names else 0
        chosen = st.selectbox("Select Bakery", all_names, index=idx)
        st.session_state.selected_bakery = chosen
        
        b_rows = df_clean[df_clean['Bakery Name'] == chosen]
        raw_flavs = b_rows['Fastelavnsbolle Type'].unique()
        flavs = sorted([str(f).strip() for f in raw_flavs if f and str(f).strip() and not str(f).isdigit()])
        
        f_sel = st.selectbox("Flavor", flavs + ["➕ New..."], key=f"f_sel_{chosen}")
        f_name = st.text_input("New flavor name:", key=f"f_in_{chosen}") if f_sel == "➕ New..." else f_sel

        mode = st.radio("Mode", ["Rate it", "Wishlist"])
        
        if mode == "Rate it":
            s = st.slider("Rating", 1.0, 5.0, 4.0, 0.25, key=f"s_{chosen}")
            p = st.number_input("Price", 0, 200, 45, key=f"p_{chosen}")
            if st.button("Submit ✅", use_container_width=True):
                new_row = [chosen, f_name, "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", s, p]
                ws.append_row(new_row, value_input_option='USER_ENTERED')
                st.toast(f"Success! Rated {chosen} ⭐{s}", icon='🥯')
                st.cache_data.clear()
                time.sleep(1) # Brief pause so they see the toast
                st.rerun()
        else:
            if st.button("Add to Wishlist ❤️", use_container_width=True):
                wish_row = [chosen, "Wishlist", "", b_rows.iloc[0]['Address'], b_rows.iloc[0]['lat'], b_rows.iloc[0]['lon'], "", "Other", "User", 0.1, 0]
                ws.append_row(wish_row, value_input_option='USER_ENTERED')
                st.toast(f"Added {chosen} to Wishlist!", icon='❤️')
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# --- 4. MAIN UI ---
st.title("🥐 Copenhagen Bakery Explorer")
t1, t2, t3 = st.tabs(["📍 Map", "📝 Checklist", "🏆 Podium"])

with t1:
    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="CartoDB positron")
    for name in display_df['Bakery Name'].unique():
        row = display_df[display_df['Bakery Name'] == name].iloc[0]
        max_r = bakery_max_rating.get(name, 0)
        
        if name == best_value_bakery: color, icon = "orange", "usd"
        elif name in top_3: color, icon = ["beige", "lightgray", "darkred"][top_3.index(name)], "star"
        elif max_r >= 1.0: color, icon = "green", "cutlery"
        elif 0.01 < max_r < 1.0: color, icon = "red", "heart"
        else: color, icon = "blue", "info-sign"
        
        folium.Marker([row['lat'], row['lon']], tooltip=name, icon=folium.Icon(color=color, icon=icon)).add_to(m)
    
    map_output = st_folium(m, width=1100, height=500, key="main_map")
    if map_output and map_output.get("last_object_clicked_tooltip"):
        clicked = map_output["last_object_clicked_tooltip"]
        if clicked != st.session_state.selected_bakery:
            st.session_state.selected_bakery = clicked
            st.rerun()

with t2:
    st.subheader("Progress Checklist")
    check_data = []
    for n in sorted(display_df['Bakery Name'].unique()):
        r = bakery_max_rating.get(n, 0)
        status = "✅ Tried" if r >= 1.0 else "❤️ Wishlist" if 0.01 < r < 1.0 else "⭕ To Visit"
        revs = int(stats.loc[n, 'Rating_Count']) if n in stats.index else 0
        check_data.append({"Bakery": n, "Status": status, "Reviews": revs})
    st.dataframe(pd.DataFrame(check_data), use_container_width=True, hide_index=True)

with t3:
    if not stats.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🏆 Top Rated")
            st.dataframe(stats.sort_values('Avg_Rating', ascending=False))
        with c2:
            st.subheader("💰 Best Value")
            if best_value_bakery:
                st.metric(best_value_bakery, f"{stats.loc[best_value_bakery, 'Avg_Rating']:.2f} Stars", 
                          delta=f"{stats.loc[best_value_bakery, 'Avg_Price']:.0f} DKK")
