import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import numpy as np
import cloudinary
import cloudinary.uploader

# ─────────────────────────────────────────────
# 1. PAGE CONFIG & MOBILE-FRIENDLY CSS
# ─────────────────────────────────────────────
st.set_page_config(page_title="BolleQuest", page_icon="🥐", layout="wide")

st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* ── Header ── */
.bq-header {
    background: linear-gradient(135deg, #1a0a00 0%, #3d1a00 60%, #7a3300 100%);
    border-radius: 16px;
    padding: 20px 28px 16px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 8px 32px rgba(122,51,0,0.3);
}
.bq-header h1 {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    color: #ffb347;
    margin: 0;
    letter-spacing: -0.5px;
}
.bq-header p { color: #c8895a; margin: 0; font-size: 0.9rem; }

/* ── Stat cards ── */
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.stat-card {
    background: #fff8f2;
    border: 1.5px solid #ffe0c0;
    border-radius: 12px;
    padding: 12px 18px;
    flex: 1;
    min-width: 120px;
    text-align: center;
}
.stat-card .val { font-family: 'Syne', sans-serif; font-size: 1.6rem; color: #b84a00; }
.stat-card .lbl { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }

/* ── Badge pill ── */
.badge {
    display: inline-block;
    background: linear-gradient(90deg, #ffb347, #ff7e00);
    color: #3d1a00;
    font-weight: 700;
    font-size: 0.72rem;
    border-radius: 20px;
    padding: 3px 10px;
    margin: 2px 3px;
    letter-spacing: 0.3px;
}
.badge-silver { background: linear-gradient(90deg, #d0d0d0, #a0a0a0); color: #222; }
.badge-gold   { background: linear-gradient(90deg, #ffe066, #ffb700); color: #3d1a00; }
.badge-best   { background: linear-gradient(90deg, #43e97b, #38f9d7); color: #064e3b; }

/* ── Review card ── */
.review-card {
    background: #fff;
    border: 1.5px solid #ffe0c0;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 8px rgba(184,74,0,0.06);
}
.review-card .meta { color: #b84a00; font-size: 0.82rem; margin-bottom: 6px; }
.review-card .stars { font-size: 1.1rem; }
.review-card .comment { color: #444; margin-top: 8px; font-size: 0.93rem; }

/* ── Filter panel ── */
.filter-panel {
    background: #fff8f2;
    border: 1.5px solid #ffe0c0;
    border-radius: 14px;
    padding: 16px 20px;
    margin-bottom: 16px;
}

/* ── Wish list ── */
.wish-tag {
    background: #fff0f0;
    border: 1px solid #ffcccc;
    color: #cc2200;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.78rem;
    margin: 2px;
    display: inline-block;
}

/* ── Mobile: tighten padding ── */
@media (max-width: 640px) {
    .bq-header h1 { font-size: 1.4rem; }
    .stat-card .val { font-size: 1.2rem; }
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 2. HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="bq-header">
  <div style="font-size:2.6rem">🥐</div>
  <div>
    <h1>BolleQuest</h1>
    <p>Copenhagen's Fastelavnsbolle tracker — find, rate, celebrate</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 3. HELPERS
# ─────────────────────────────────────────────
def get_now_dk():
    return datetime.now(pytz.timezone('Europe/Copenhagen'))

def stars(rating):
    full = int(round(rating))
    return "⭐" * full + "☆" * (5 - full)

def compute_badges(user_reviews: pd.DataFrame) -> list[str]:
    """Return list of badge HTML strings for a user."""
    badges = []
    n = len(user_reviews)
    if n >= 1:   badges.append('<span class="badge">🥐 First Bite</span>')
    if n >= 5:   badges.append('<span class="badge badge-silver">🔍 Bolle Scout</span>')
    if n >= 10:  badges.append('<span class="badge badge-gold">🏆 Bolle Veteran</span>')
    if n >= 25:  badges.append('<span class="badge badge-gold">👑 Bolle Legend</span>')

    # Early Bird: any review before 09:00
    early = user_reviews[user_reviews['Time'] < "09:00"]
    if not early.empty:
        badges.append('<span class="badge">🌅 Early Bird</span>')

    # Adventurer: 5+ different bakeries
    if user_reviews['Bakery Name'].nunique() >= 5:
        badges.append('<span class="badge badge-silver">🗺️ Adventurer</span>')

    # Photographer: uploaded at least one photo
    if user_reviews['Photo URL'].astype(str).str.startswith('http').any():
        badges.append('<span class="badge">📸 Shutterbug</span>')

    return badges

# ─────────────────────────────────────────────
# 4. SESSION STATE
# ─────────────────────────────────────────────
defaults = {
    "arrival_times": {},
    "selected_bakery": None,
    "merchant_bakery": None,
    "user_nickname": "BunHunter",
    "review_mode": None,
    "user_filter": None,
    "wish_list": [],         # list of bakery names
    "show_filters": False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ─────────────────────────────────────────────
# 5. DATA CONNECTION
# ─────────────────────────────────────────────
@st.cache_resource
def get_gs_client():
    creds_dict = st.secrets["connections"]["my_bakery_db"]
    return gspread.service_account_from_dict(creds_dict)

def get_worksheet():
    return get_gs_client().open_by_key(
        "1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo"
    ).get_worksheet(0)

@st.cache_data(ttl=45)   # 45 s — sane for Sheets API quota
def load_data():
    try:
        data = get_worksheet().get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df.columns = [c.strip() for c in df.columns]
        num_cols = ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']
        str_cols = ['Photo URL', 'Comment', 'Fastelavnsbolle Type', 'Bakery Name',
                    'Address', 'Date', 'Time', 'Category', 'User', 'Bakery Key']
        for col in num_cols:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        for col in str_cols:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"Data sync error: {e}")
        return pd.DataFrame()

df_raw = load_data()

# ─────────────────────────────────────────────
# 6. CLOUDINARY CONFIG
# ─────────────────────────────────────────────
try:
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
    )
    _cloudinary_ok = True
except Exception:
    _cloudinary_ok = False

def upload_photo(file) -> str:
    """Upload to Cloudinary and return secure URL, or '' on failure."""
    if not _cloudinary_ok or file is None:
        return ""
    try:
        result = cloudinary.uploader.upload(
            file,
            folder="bollquest",
            transformation=[{"width": 800, "crop": "limit", "quality": "auto"}],
        )
        return result.get("secure_url", "")
    except Exception as e:
        st.warning(f"Photo upload failed: {e}")
        return ""

# ─────────────────────────────────────────────
# 7. WRITE TO SHEETS
# ─────────────────────────────────────────────
def post_to_sheets(row_list):
    sanitized = []
    for item in row_list:
        if isinstance(item, (np.int64, np.int32)):    sanitized.append(int(item))
        elif isinstance(item, (np.float64, np.float32)): sanitized.append(float(item))
        elif item is None or (isinstance(item, float) and np.isnan(item)):
            sanitized.append("")
        else:
            sanitized.append(str(item))
    get_worksheet().append_row(sanitized, value_input_option='USER_ENTERED')

# ─────────────────────────────────────────────
# 8. DERIVED METRICS
# ─────────────────────────────────────────────
def bakery_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-bakery stats including Best Value score."""
    if df.empty:
        return pd.DataFrame()
    grp = df[df['Rating'] > 0].groupby('Bakery Name').agg(
        avg_rating=('Rating', 'mean'),
        review_count=('Rating', 'count'),
        avg_wait=('Wait Time', 'mean'),
        avg_price=('Price', 'mean'),
        latest_stock=('Stock', 'last'),
        latest_flavor=('Fastelavnsbolle Type', 'last'),
    ).reset_index()
    # Best Value = rating / log(price+1)  — rewards high rating at low price
    grp['value_score'] = grp.apply(
        lambda r: r['avg_rating'] / np.log1p(max(r['avg_price'], 1)), axis=1
    )
    return grp.sort_values('avg_rating', ascending=False)

stats_df = bakery_stats(df_raw) if not df_raw.empty else pd.DataFrame()
best_value_bakery = (
    stats_df.sort_values('value_score', ascending=False).iloc[0]['Bakery Name']
    if not stats_df.empty else None
)

# ─────────────────────────────────────────────
# 9. TODAY'S SUMMARY CARDS
# ─────────────────────────────────────────────
today_str = get_now_dk().strftime("%Y-%m-%d")
if not df_raw.empty:
    today_df = df_raw[df_raw['Date'] == today_str]
    total_reviews_today = len(today_df)
    avg_rating_today = today_df['Rating'].mean() if not today_df.empty else 0
    top_flavor_today = (
        today_df['Fastelavnsbolle Type'].value_counts().index[0]
        if not today_df.empty else "—"
    )
    in_stock_count = int((df_raw.groupby('Bakery Name')['Stock'].last() > 0).sum())

    st.markdown(f"""
    <div class="stat-row">
      <div class="stat-card"><div class="val">{total_reviews_today}</div><div class="lbl">Reviews Today</div></div>
      <div class="stat-card"><div class="val">{avg_rating_today:.1f} ⭐</div><div class="lbl">Avg Rating</div></div>
      <div class="stat-card"><div class="val">{in_stock_count}</div><div class="lbl">In Stock Now</div></div>
      <div class="stat-card"><div class="val" style="font-size:1rem">{top_flavor_today[:14]}</div><div class="lbl">Trending Flavor</div></div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 10. TABS
# ─────────────────────────────────────────────
t_map, t_stream, t_top, t_wishlist, t_settings, t_help = st.tabs(
    ["📍 Map", "🧵 Stream", "🏆 Rankings", "💛 Wish List", "⚙️ Settings", "❓ Help"]
)

# ══════════════════════════════════════════════
# TAB: MAP
# ══════════════════════════════════════════════
with t_map:

    # ── Filters ──────────────────────────────
    with st.expander("🎛️ Filters", expanded=False):
        st.markdown('<div class="filter-panel">', unsafe_allow_html=True)
        col_s, col_r, col_p = st.columns(3)
        with col_s:
            search_q = st.text_input("🔍 Search bakery / flavor", "").lower().strip()
        with col_r:
            min_rating = st.slider("⭐ Min rating", 0.0, 5.0, 0.0, 0.5)
        with col_p:
            max_price = st.slider("💰 Max price (DKK)", 10, 200, 200, 5)
        hide_sold_out = st.checkbox("🚫 Hide sold-out bakeries", value=False)
        st.markdown('</div>', unsafe_allow_html=True)

    # Apply filters
    filtered = df_raw.copy()
    if not filtered.empty:
        if search_q:
            corpus = (
                filtered['Bakery Name'].astype(str) + " " +
                filtered['Fastelavnsbolle Type'].astype(str)
            ).str.lower()
            filtered = filtered[corpus.str.contains(search_q, na=False)]
        if min_rating > 0:
            # Only filter bakeries that have at least one review meeting the threshold
            passing = (
                filtered[filtered['Rating'] >= min_rating]['Bakery Name'].unique()
                if min_rating > 0 else filtered['Bakery Name'].unique()
            )
            filtered = filtered[filtered['Bakery Name'].isin(passing)]
        if max_price < 200:
            filtered = filtered[filtered['Price'] <= max_price]
        if hide_sold_out:
            filtered = filtered[filtered['Stock'] > 0]

    # ── Action Panel (selected bakery) ────────
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_rows = df_raw[df_raw['Bakery Name'] == name]
        if b_rows.empty:
            st.session_state.selected_bakery = None
        else:
            b_data = b_rows.iloc[-1]   # most recent entry
            is_merchant = st.session_state.merchant_bakery == name
            is_best_value = (best_value_bakery == name)
            on_wish_list = name in st.session_state.wish_list

            # Bakery headline
            title_extra = ""
            if is_best_value:
                title_extra += ' <span class="badge badge-best">💚 Best Value</span>'
            if is_merchant:
                title_extra += ' <span class="badge">🧑‍🍳 YOUR SHOP</span>'

            st.markdown(f"#### 📍 {name} {title_extra}", unsafe_allow_html=True)

            # Per-bakery aggregated stats
            if not stats_df.empty and name in stats_df['Bakery Name'].values:
                bk = stats_df[stats_df['Bakery Name'] == name].iloc[0]
                st.markdown(f"""
                <div class="stat-row">
                  <div class="stat-card"><div class="val">{bk['avg_rating']:.1f} ⭐</div><div class="lbl">Avg Rating</div></div>
                  <div class="stat-card"><div class="val">{int(bk['review_count'])}</div><div class="lbl">Reviews</div></div>
                  <div class="stat-card"><div class="val">{int(bk['avg_wait'])}m</div><div class="lbl">Avg Wait</div></div>
                  <div class="stat-card"><div class="val">{int(bk['avg_price'])} kr</div><div class="lbl">Avg Price</div></div>
                </div>
                """, unsafe_allow_html=True)

            # Wish list toggle
            wl_label = "💛 Remove from Wish List" if on_wish_list else "🤍 Add to Wish List"
            if st.button(wl_label, key="wl_toggle"):
                if on_wish_list:
                    st.session_state.wish_list.remove(name)
                else:
                    st.session_state.wish_list.append(name)
                st.rerun()

            st.divider()

            # ── MERCHANT VIEW ─────────────────
            if is_merchant:
                st.subheader("🧑‍🍳 Update Your Shop")
                with st.form("merchant_update"):
                    new_stock  = st.number_input("Current Stock", 0, 1000, int(b_data['Stock']))
                    new_flavor = st.text_input("Today's Featured Flavor", value=str(b_data['Fastelavnsbolle Type']))
                    new_price  = st.number_input("Price (DKK)", 0, 200, int(b_data['Price']))
                    m_comm     = st.text_area("Merchant Note", value="Freshly restocked!")
                    if st.form_submit_button("📡 Broadcast Update"):
                        row = [name, new_flavor, "", str(b_data['Address']),
                               float(b_data['lat']), float(b_data['lon']),
                               get_now_dk().strftime("%Y-%m-%d"), "Merchant", name,
                               5.0, new_price, new_stock,
                               get_now_dk().strftime("%H:%M"), "", m_comm, 0]
                        post_to_sheets(row)
                        st.cache_data.clear()
                        st.success("Broadcast sent!")
                        st.rerun()

            # ── USER VIEW ─────────────────────
            else:
                if b_data['Stock'] <= 0:
                    st.error(f"### 🚫 SOLD OUT at {name}")
                    st.info(f"Last reported flavor: **{b_data['Fastelavnsbolle Type']}**")
                else:
                    st.success(f"✅ In Stock — {int(b_data['Stock'])} available · {b_data['Fastelavnsbolle Type']}")

                    # Choose path: join line or fast review
                    if (name not in st.session_state.arrival_times
                            and st.session_state.review_mode != "instant"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("🏁 Join the Queue", use_container_width=True):
                                st.session_state.arrival_times[name] = {
                                    "start": get_now_dk(), "wait": None
                                }
                                st.rerun()
                        with c2:
                            if st.button("🚀 Fast Review", use_container_width=True):
                                st.session_state.review_mode = "instant"
                                st.rerun()
                    else:
                        wait_val = 0
                        show_form = False

                        if st.session_state.review_mode == "instant":
                            show_form = True
                        elif name in st.session_state.arrival_times:
                            entry = st.session_state.arrival_times[name]
                            if entry["wait"] is None:
                                w_now = (get_now_dk() - entry["start"]).seconds // 60
                                st.info(f"⏱️ In queue: **{w_now} min** so far…")
                                if st.button("🛍️ Got my bolle!", type="primary"):
                                    st.session_state.arrival_times[name]["wait"] = max(1, w_now)
                                    st.rerun()
                            else:
                                show_form = True
                                wait_val = entry["wait"]

                        if show_form:
                            with st.form("final_review", clear_on_submit=False):
                                st.markdown("**📸 Add a photo** *(optional — taken with your camera or uploaded)*")
                                uploaded_file = st.file_uploader(
                                    "Photo", type=['jpg', 'jpeg', 'png', 'webp'],
                                    label_visibility="collapsed"
                                )
                                t_f = st.text_input("Flavor", value=str(b_data['Fastelavnsbolle Type']))
                                t_r = st.slider("Your Rating ⭐", 1.0, 5.0, 3.0, 0.25)
                                t_p = st.number_input("Price paid (DKK)", 0, 200, int(b_data['Price']))
                                t_c = st.text_area("Your review", placeholder="Flaky, sweet, cream-filled perfection…")

                                if st.form_submit_button("✅ Submit Review", type="primary", use_container_width=True):
                                    with st.spinner("Uploading…"):
                                        photo_url = upload_photo(uploaded_file)
                                    row = [name, t_f, photo_url, str(b_data['Address']),
                                           float(b_data['lat']), float(b_data['lon']),
                                           get_now_dk().strftime("%Y-%m-%d"), "User",
                                           str(st.session_state.user_nickname),
                                           float(t_r), float(t_p), int(b_data['Stock']),
                                           get_now_dk().strftime("%H:%M"), "", str(t_c),
                                           int(wait_val)]
                                    post_to_sheets(row)
                                    # Clear state
                                    if name in st.session_state.arrival_times:
                                        del st.session_state.arrival_times[name]
                                    st.session_state.review_mode = None
                                    st.session_state.selected_bakery = None
                                    st.cache_data.clear()
                                    st.balloons()
                                    # Check for new badges
                                    new_df = load_data()
                                    user_revs = new_df[new_df['User'] == st.session_state.user_nickname]
                                    new_badges = compute_badges(user_revs)
                                    if new_badges:
                                        st.success("🎉 New badge unlocked!")
                                    st.rerun()

            if st.button("✖ Cancel", use_container_width=True):
                if name in st.session_state.arrival_times:
                    del st.session_state.arrival_times[name]
                st.session_state.review_mode = None
                st.session_state.selected_bakery = None
                st.rerun()

            st.divider()

    # ── MAP — hidden while a bakery panel is open ─────────────────────────
    if not st.session_state.selected_bakery:
        if not filtered.empty:
            latest = (
                filtered.sort_values(['Bakery Name', 'Date', 'Time'])
                .groupby('Bakery Name')
                .last()
                .reset_index()
            )
        else:
            latest = pd.DataFrame()

        m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")

        for _, r in latest.dropna(subset=['lat', 'lon']).iterrows():
            if r['lat'] == 0 and r['lon'] == 0:
                continue
            sold_out = r['Stock'] <= 0
            is_bv    = r['Bakery Name'] == best_value_bakery
            color    = "red" if sold_out else ("green" if not is_bv else "darkgreen")
            icon_sym = "times" if sold_out else ("star" if is_bv else "shopping-basket")
            folium.Marker(
                [r['lat'], r['lon']],
                tooltip=r['Bakery Name'],
                icon=folium.Icon(color=color, icon=icon_sym, prefix='fa'),
            ).add_to(m)

        res = st_folium(m, width="100%", height=480, key="main_map")
        if res.get("last_object_clicked_tooltip"):
            clicked = res["last_object_clicked_tooltip"]
            if st.session_state.selected_bakery != clicked:
                st.session_state.selected_bakery = clicked
                st.rerun()

        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

# ══════════════════════════════════════════════
# TAB: STREAM
# ══════════════════════════════════════════════
with t_stream:
    st.subheader("🧵 Live Feed")

    if st.session_state.user_filter:
        st.info(f"Showing posts by **@{st.session_state.user_filter}**")
        if st.button("✖ Clear Filter"):
            st.session_state.user_filter = None
            st.rerun()

    if not df_raw.empty:
        s_df = df_raw[df_raw['Category'] == 'User'].sort_values(
            by=["Date", "Time"], ascending=False
        )
        if st.session_state.user_filter:
            s_df = s_df[s_df['User'] == st.session_state.user_filter]

        if s_df.empty:
            st.info("No user reviews yet — be the first!")
        else:
            for _, r in s_df.iterrows():
                is_bv = (r['Bakery Name'] == best_value_bakery)
                bv_tag = '<span class="badge badge-best">💚 Best Value</span>' if is_bv else ''
                photo_url = str(r.get('Photo URL', ''))
                st.markdown(f"""
                <div class="review-card">
                  <div class="meta">📍 <b>{r['Bakery Name']}</b> {bv_tag} &nbsp;·&nbsp; 👤 @{r['User']} &nbsp;·&nbsp; {r['Date']} {r['Time']}</div>
                  <div class="stars">{stars(float(r['Rating']))} &nbsp; <b>{float(r['Rating']):.1f}</b>
                       &nbsp;|&nbsp; ⏳ {int(float(r.get('Wait Time', 0)))} min wait
                       &nbsp;|&nbsp; 💰 {int(float(r['Price']))} kr</div>
                  <div>🍩 {r['Fastelavnsbolle Type']}</div>
                  {'<div class="comment">' + str(r['Comment']) + '</div>' if r['Comment'] else ''}
                </div>
                """, unsafe_allow_html=True)
                # Render photo separately — much more reliable than embedding in HTML
                if photo_url.startswith('http'):
                    st.image(photo_url, use_container_width=True)
    else:
        st.info("No data yet.")

# ══════════════════════════════════════════════
# TAB: RANKINGS / LEADERBOARD
# ══════════════════════════════════════════════
with t_top:
    st.subheader("🏆 Rankings")

    if not stats_df.empty:
        # ── Best Value Award ──────────────────
        if best_value_bakery:
            bv_row = stats_df[stats_df['Bakery Name'] == best_value_bakery].iloc[0]
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#d4f7e0,#a8f0c8);border-radius:16px;padding:20px;margin-bottom:20px;border:2px solid #38f9d7;">
              <div style="font-family:'Syne',sans-serif;font-size:1.3rem;color:#064e3b">💚 Best Value Bakery Award</div>
              <div style="font-size:1.6rem;font-weight:800;color:#065f46;margin:6px 0">{best_value_bakery}</div>
              <div style="color:#047857">⭐ {bv_row['avg_rating']:.2f} rating &nbsp;·&nbsp; 💰 {int(bv_row['avg_price'])} kr avg &nbsp;·&nbsp; {int(bv_row['review_count'])} reviews</div>
            </div>
            """, unsafe_allow_html=True)

        # ── Bakery Rankings ───────────────────
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🥐 Bakeries by Rating**")
            for _, row in stats_df.head(10).iterrows():
                is_bv = row['Bakery Name'] == best_value_bakery
                bv = " 💚" if is_bv else ""
                st.markdown(
                    f"**{row['Bakery Name']}**{bv} — {stars(row['avg_rating'])} "
                    f"({row['avg_rating']:.1f}, {int(row['review_count'])} reviews)"
                )

            st.markdown("---")
            st.markdown("**🍩 Top Flavors**")
            flavor_df = (
                df_raw[df_raw['Rating'] > 0]
                .groupby('Fastelavnsbolle Type')['Rating']
                .agg(['mean', 'count'])
                .sort_values('mean', ascending=False)
                .reset_index()
            )
            for _, row in flavor_df.head(8).iterrows():
                st.markdown(
                    f"**{row['Fastelavnsbolle Type']}** — {stars(row['mean'])} "
                    f"({row['mean']:.1f}, {int(row['count'])} reviews)"
                )

        with c2:
            st.markdown("**👑 Top Hunters**")
            u_counts = (
                df_raw[df_raw['Category'] == 'User']['User']
                .value_counts()
                .reset_index()
            )
            # Modern pandas (>=1.1) already names cols ['User', 'count']
            u_counts.columns = ['User', 'count']
            for i, row in u_counts.head(10).iterrows():
                user_revs = df_raw[df_raw['User'] == row['User']]
                badges_html = "".join(compute_badges(user_revs))
                col_a, col_b = st.columns([3, 1])
                col_a.markdown(
                    f"**@{row['User']}** — {int(row['count'])} reviews<br>{badges_html}",
                    unsafe_allow_html=True
                )
                if col_b.button("View", key=f"u_{i}"):
                    st.session_state.user_filter = row['User']
                    st.rerun()

            st.markdown("---")
            st.markdown("**💰 Best Value Scores**")
            for _, row in stats_df.sort_values('value_score', ascending=False).head(8).iterrows():
                st.markdown(
                    f"**{row['Bakery Name']}** — score {row['value_score']:.2f} "
                    f"(⭐{row['avg_rating']:.1f} / {int(row['avg_price'])}kr)"
                )
    else:
        st.info("No reviews yet. Start hunting!")

# ══════════════════════════════════════════════
# TAB: WISH LIST
# ══════════════════════════════════════════════
with t_wishlist:
    st.subheader("💛 Your Wish List")
    st.caption("Bakeries you want to visit — tap the heart icon on the map to add them.")

    if not st.session_state.wish_list:
        st.info("Your wish list is empty. Tap **🤍 Add to Wish List** on any bakery on the map!")
    else:
        for bname in st.session_state.wish_list:
            with st.container(border=True):
                col_n, col_r, col_x = st.columns([4, 2, 1])
                col_n.markdown(f"**{bname}**")

                # Show latest stock status
                if not df_raw.empty:
                    b_rows = df_raw[df_raw['Bakery Name'] == bname]
                    if not b_rows.empty:
                        last = b_rows.iloc[-1]
                        status = "🟢 In Stock" if last['Stock'] > 0 else "🔴 Sold Out"
                        col_r.markdown(status)

                if col_x.button("✖", key=f"wl_rm_{bname}"):
                    st.session_state.wish_list.remove(bname)
                    st.rerun()

# ══════════════════════════════════════════════
# TAB: SETTINGS
# ══════════════════════════════════════════════
with t_settings:
    st.subheader("⚙️ Settings")

    st.session_state.user_nickname = st.text_input(
        "Your Hunter Nickname 🎯", st.session_state.user_nickname
    )

    # Show user's own badges
    if not df_raw.empty:
        my_revs = df_raw[df_raw['User'] == st.session_state.user_nickname]
        my_badges = compute_badges(my_revs)
        if my_badges:
            st.markdown("**Your Badges:**")
            st.markdown(" ".join(my_badges), unsafe_allow_html=True)
        else:
            st.info("No badges yet — submit your first review to earn one!")

    st.divider()
    st.markdown("**Merchant Access**")
    if st.session_state.merchant_bakery:
        st.success(f"✅ Logged in as merchant: **{st.session_state.merchant_bakery}**")
        if st.button("🚪 Log Out"):
            st.session_state.merchant_bakery = None
            st.rerun()
    else:
        k_in = st.text_input("Bakery Secret Key", type="password")
        if st.button("🔑 Unlock Merchant Tools"):
            if not df_raw.empty:
                match = df_raw[df_raw['Bakery Key'].astype(str) == k_in]
                if not match.empty:
                    st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                    st.rerun()
                else:
                    st.error("Key not recognised.")

# ══════════════════════════════════════════════
# TAB: HELP
# ══════════════════════════════════════════════
with t_help:
    st.markdown("""
### 🥐 How to use BolleQuest

**Finding bolles**
- Green pins = in stock, Red pins = sold out, **Dark green ★ = Best Value bakery**
- Use the 🎛️ Filters panel to narrow by rating, price, or search by name/flavor
- Tap any pin to see stock, average rating, and wait times

**Reviewing**
- Tap a green pin → choose **Join the Queue** (we time your wait) or **Fast Review**
- Add a photo straight from your phone camera
- Your review updates the live feed and rankings instantly

**Wish List**
- Tap 🤍 on any bakery to save it to your Wish List tab for later

**Badges you can earn** 🏅
| Badge | How |
|---|---|
| 🥐 First Bite | Submit your first review |
| 🔍 Bolle Scout | 5 reviews |
| 🏆 Bolle Veteran | 10 reviews |
| 👑 Bolle Legend | 25 reviews |
| 🌅 Early Bird | Review before 9 AM |
| 🗺️ Adventurer | Visit 5+ different bakeries |
| 📸 Shutterbug | Upload a photo |

**Best Value Award 💚**
Awarded to the bakery with the highest rating-to-price ratio. Updated live.

**For bakeries**
Enter your secret key in ⚙️ Settings to unlock merchant tools and broadcast stock updates.
    """)
