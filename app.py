import streamlit as st
import streamlit.components.v1 as components
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
import html
import hashlib

# ─────────────────────────────────────────────
# 1. PAGE CONFIG & CSS
# ─────────────────────────────────────────────
st.set_page_config(page_title="BolleQuest", page_icon="🥐", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.bq-header {
    background: linear-gradient(135deg, #1a0a00 0%, #3d1a00 60%, #7a3300 100%);
    border-radius: 16px; padding: 20px 28px 16px; margin-bottom: 20px;
    display: flex; align-items: center; gap: 16px;
    box-shadow: 0 8px 32px rgba(122,51,0,0.3);
}
.bq-header h1 { font-family: 'Syne', sans-serif; font-size: 2rem; color: #ffb347; margin: 0; letter-spacing: -0.5px; }
.bq-header p  { color: #c8895a; margin: 0; font-size: 0.9rem; }

.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.stat-card {
    background: #fff8f2; border: 1.5px solid #ffe0c0; border-radius: 12px;
    padding: 12px 18px; flex: 1; min-width: 120px; text-align: center;
}
.stat-card .val { font-family: 'Syne', sans-serif; font-size: 1.6rem; color: #b84a00; }
.stat-card .lbl { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }

.badge {
    display: inline-block; background: linear-gradient(90deg, #ffb347, #ff7e00);
    color: #3d1a00; font-weight: 700; font-size: 0.72rem;
    border-radius: 20px; padding: 3px 10px; margin: 2px 3px; letter-spacing: 0.3px;
}
.badge-silver { background: linear-gradient(90deg, #d0d0d0, #a0a0a0); color: #222; }
.badge-gold   { background: linear-gradient(90deg, #ffe066, #ffb700); color: #3d1a00; }
.badge-best   { background: linear-gradient(90deg, #43e97b, #38f9d7); color: #064e3b; }

.review-card {
    background: #fff; border: 1.5px solid #ffe0c0; border-radius: 14px;
    padding: 16px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(184,74,0,0.06);
}
.review-card .meta   { color: #b84a00; font-size: 0.82rem; margin-bottom: 6px; }
.review-card .stars  { font-size: 1.1rem; }
.review-card .comment{ color: #444; margin-top: 8px; font-size: 0.93rem; }

.onboarding-banner {
    background: linear-gradient(135deg, #fff8f2, #ffe8cc);
    border: 2px solid #ffb347; border-radius: 16px; padding: 18px 22px; margin-bottom: 16px;
}

@media (max-width: 640px) {
    .bq-header h1 { font-size: 1.4rem; }
    .stat-card .val { font-size: 1.2rem; }
}
</style>
""", unsafe_allow_html=True)

# Add to Home Screen — simple informational banner (no PWA manifest needed)
if not st.session_state.get("a2hs_dismissed"):
    cols = st.columns([10, 1])
    with cols[0]:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1a0a00,#3d1a00);color:#ffb347;
                    padding:12px 18px;border-radius:12px;font-family:sans-serif;font-size:14px;
                    display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          📱 <b>Add to your home screen:</b>
          <span style="color:#ffd580">iPhone: tap <b>Share ↑</b> → "Add to Home Screen"</span>
          &nbsp;·&nbsp;
          <span style="color:#ffd580">Android: tap <b>⋮ menu</b> → "Add to Home Screen" *(may be under "More options")*</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[1]:
        if st.button("✕", key="a2hs_dismiss", help="Dismiss"):
            st.session_state.a2hs_dismissed = True
            st.rerun()

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

def esc(s):
    """HTML-escape user-supplied strings to prevent XSS."""
    return html.escape(str(s))

def stars(rating):
    full = int(round(rating))
    return "⭐" * full + "☆" * (5 - full)

def hash_key(k):
    return hashlib.sha256(str(k).encode()).hexdigest()

def compute_badges(user_reviews: pd.DataFrame) -> list[str]:
    badges = []
    n = len(user_reviews)
    if n >= 1:  badges.append('<span class="badge">🥐 First Bite</span>')
    if n >= 5:  badges.append('<span class="badge badge-silver">🔍 Bolle Scout</span>')
    if n >= 10: badges.append('<span class="badge badge-gold">🏆 Bolle Veteran</span>')
    if n >= 25: badges.append('<span class="badge badge-gold">👑 Bolle Legend</span>')
    if not user_reviews[user_reviews['Time'] < "09:00"].empty:
        badges.append('<span class="badge">🌅 Early Bird</span>')
    if user_reviews['Bakery Name'].nunique() >= 5:
        badges.append('<span class="badge badge-silver">🗺️ Adventurer</span>')
    if user_reviews['Photo URL'].astype(str).str.startswith('http').any():
        badges.append('<span class="badge">📸 Shutterbug</span>')
    return badges

def share_text(bakery, rating, url="https://bollequest.streamlit.app"):
    return f"I rated {bakery} ⭐{rating:.1f} on BolleQuest! {url}"

# ─────────────────────────────────────────────
# 4. SESSION STATE
# ─────────────────────────────────────────────
defaults = {
    "arrival_times": {},
    "selected_bakery": None,
    "merchant_bakery": None,
    "user_nickname": "",
    "review_mode": None,
    "user_filter": None,
    "wish_list": [],
    "onboarding_done": False,
    "nickname_set": False,
    "a2hs_dismissed": False,
    "show_coupon": None,   # bakery name whose coupon is being shown
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# Persist nickname + wish list via localStorage
components.html("""
<script>
// On load: push saved values up to Streamlit via query params
const nick = localStorage.getItem('bq_nickname');
const wl   = localStorage.getItem('bq_wishlist');
if (nick) {
    const inp = window.parent.document.querySelector('input[aria-label="nickname_restore"]');
    if (inp) { inp.value = nick; inp.dispatchEvent(new Event('input', {bubbles:true})); }
}
</script>
""", height=0)

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

def get_discounts_worksheet():
    """Returns worksheet index 1 (Discounts). Creates it if missing."""
    wb = get_gs_client().open_by_key("1gZfSgfa9xHLentpYHcoTb4rg_RJv2HItHcco85vNwBo")
    sheets = wb.worksheets()
    if len(sheets) < 2:
        ws = wb.add_worksheet(title="Discounts", rows=200, cols=6)
        ws.append_row(["Bakery Name", "Discount Pct", "Description", "Valid Until", "Active"])
        return ws
    return sheets[1]

@st.cache_data(ttl=60)
def load_discounts():
    try:
        data = get_discounts_worksheet().get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=["Bakery Name","Discount Pct","Description","Valid Until","Active"])
        df.columns = [c.strip() for c in df.columns]
        df["Discount Pct"] = pd.to_numeric(df.get("Discount Pct", 0), errors='coerce').fillna(0)
        for c in ["Description","Valid Until","Active","Bakery Name"]:
            if c not in df.columns: df[c] = ""
            df[c] = df[c].astype(str)
        return df
    except Exception:
        return pd.DataFrame(columns=["Bakery Name","Discount Pct","Description","Valid Until","Active"])

def save_discount(bakery_name, pct, description, valid_until):
    """Overwrite the existing row for this bakery, or append a new one."""
    ws = get_discounts_worksheet()
    data = ws.get_all_values()
    for i, row in enumerate(data[1:], start=2):  # row 1 is header
        if row and row[0] == bakery_name:
            ws.update(f"A{i}:E{i}", [[bakery_name, pct, description, valid_until, "1"]])
            return
    ws.append_row([bakery_name, pct, description, valid_until, "1"])

@st.cache_data(ttl=45)
def load_data():
    try:
        data = get_worksheet().get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df.columns = [c.strip() for c in df.columns]
        num_cols = ['lat', 'lon', 'Stock', 'Price', 'Rating', 'Wait Time']
        str_cols = ['Photo URL', 'Comment', 'Fastelavnsbolle Type', 'Bakery Name',
                    'Address', 'Date', 'Time', 'Category', 'User', 'Bakery Key',
                    'Opening Hours']
        for col in num_cols:
            if col not in df.columns: df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        for col in str_cols:
            if col not in df.columns: df[col] = ""
            df[col] = df[col].astype(str)
        # Hash any unhashed bakery keys (idempotent — already-hashed values are 64 hex chars)
        if 'Bakery Key' in df.columns:
            df['Bakery Key'] = df['Bakery Key'].apply(
                lambda k: k if len(k) == 64 else hash_key(k)
            )
        return df
    except Exception as e:
        st.error(f"Data sync error: {e}")
        return pd.DataFrame()

df_raw = load_data()
disc_df = load_discounts()

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
    if not _cloudinary_ok or file is None:
        return ""
    try:
        result = cloudinary.uploader.upload(
            file, folder="bollquest",
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
        if isinstance(item, (np.int64, np.int32)):        sanitized.append(int(item))
        elif isinstance(item, (np.float64, np.float32)):  sanitized.append(float(item))
        elif item is None or (isinstance(item, float) and np.isnan(item)):
            sanitized.append("")
        else:
            sanitized.append(str(item))
    get_worksheet().append_row(sanitized, value_input_option='USER_ENTERED')

# ─────────────────────────────────────────────
# 8. DERIVED METRICS
# ─────────────────────────────────────────────
def bakery_stats(df: pd.DataFrame) -> pd.DataFrame:
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
    # Only user reviews for stats (exclude merchant broadcasts which use Rating=5.0)
    today_df = df_raw[(df_raw['Date'] == today_str) & (df_raw['Category'] == 'User')]
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
      <div class="stat-card"><div class="val" style="font-size:1rem">{top_flavor_today[:18]}</div><div class="lbl">Trending Flavor</div></div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 10. NICKNAME PROMPT (shown above tabs when name not yet set)
# ─────────────────────────────────────────────
if not st.session_state.user_nickname.strip():
    with st.container(border=True):
        st.markdown("**👋 What should we call you?**")
        st.caption("Your nickname appears on reviews and the leaderboard. You can change it anytime in Settings.")
        col_n, col_b = st.columns([4, 1])
        welcome_nick = col_n.text_input("Nickname", label_visibility="collapsed",
                                        placeholder="e.g. CreamPuffCarla", key="welcome_nick")
        if col_b.button("Let's go! 🥐", use_container_width=True):
            if welcome_nick.strip():
                st.session_state.user_nickname = welcome_nick.strip()
                components.html(
                    f"<script>localStorage.setItem('bq_nickname','{html.escape(welcome_nick.strip())}');</script>",
                    height=0
                )
                st.rerun()

# ─────────────────────────────────────────────
# 11. TABS
# ─────────────────────────────────────────────
t_map, t_stream, t_top, t_wishlist, t_discounts, t_settings, t_help = st.tabs(
    ["📍 Map", "🧵 Stream", "🏆 Rankings", "💛 Wish List", "🏷️ Discounts", "⚙️ Settings", "❓ Help"]
)

# ══════════════════════════════════════════════
# TAB: MAP
# ══════════════════════════════════════════════
with t_map:

    # ── Onboarding banner (first visit only) ──
    if not st.session_state.onboarding_done:
        st.markdown("""
        <div class="onboarding-banner">
          <b style="font-size:1.1rem">👋 Welcome to BolleQuest!</b><br>
          <span style="color:#666">Track Copenhagen's fastelavnsbolle in real time — find bakeries on the map,
          join the queue, rate your bolle, and earn badges. Green pins = in stock,
          red = sold out, dark green ★ = best value.</span>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Got it! 🥐", key="onboarding_dismiss"):
            st.session_state.onboarding_done = True
            st.rerun()

    # ── Filters ───────────────────────────────
    with st.expander("🎛️ Filters", expanded=False):
        col_s, col_r, col_p = st.columns(3)
        with col_s:
            search_q = st.text_input("🔍 Search bakery / flavor", "").lower().strip()
        with col_r:
            min_rating = st.slider("⭐ Min rating", 0.0, 5.0, 0.0, 0.5)
        with col_p:
            max_price = st.slider("💰 Max price (DKK)", 10, 200, 200, 5)
        hide_sold_out = st.checkbox("🚫 Hide sold-out bakeries", value=False)

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
            passing = filtered[filtered['Rating'] >= min_rating]['Bakery Name'].unique()
            filtered = filtered[filtered['Bakery Name'].isin(passing)]
        if max_price < 200:
            filtered = filtered[filtered['Price'] <= max_price]
        if hide_sold_out:
            latest_stock = (
                filtered.sort_values(['Bakery Name', 'Date', 'Time'])
                .groupby('Bakery Name')['Stock'].last()
            )
            in_stock_bakeries = latest_stock[latest_stock > 0].index
            filtered = filtered[filtered['Bakery Name'].isin(in_stock_bakeries)]

    # ── Action strip ──────────────────────────
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_rows = df_raw[df_raw['Bakery Name'] == name]
        if not b_rows.empty:
            b_data     = b_rows.iloc[-1]
            sold_out   = b_data['Stock'] <= 0
            in_queue   = name in st.session_state.arrival_times
            in_fast    = st.session_state.review_mode == "instant"
            got_bolle  = in_queue and st.session_state.arrival_times[name].get("wait") is not None

            stock_badge = "🔴 Sold out" if sold_out else f"🟢 {int(b_data['Stock'])} left"
            st.markdown(f"""
            <div style="background:#fff8f2;border:2px solid #ffb347;border-radius:14px;
                        padding:14px 18px;margin-bottom:10px;">
              <div style="font-size:1.1rem;font-weight:700;color:#3d1a00">
                📍 {esc(name)} &nbsp;
                <span style="font-size:0.85rem;font-weight:400;color:#888">
                  {stock_badge} · 🍩 {esc(b_data['Fastelavnsbolle Type'])} · 💰 {int(b_data['Price'])} kr
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if not sold_out and not in_queue and not in_fast:
                ca, cb, cc = st.columns([2, 2, 1])
                with ca:
                    if st.button("🏁 Join the Queue", use_container_width=True, key="strip_queue"):
                        st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}
                        st.rerun()
                with cb:
                    if st.button("🚀 Fast Review", use_container_width=True, key="strip_fast"):
                        st.session_state.review_mode = "instant"
                        st.rerun()
                with cc:
                    if st.button("✖", use_container_width=True, key="strip_close"):
                        st.session_state.selected_bakery = None
                        st.rerun()
                st.caption("*Queue: we time your wait · Fast: already eaten? Skip straight to the review*")

            elif in_queue and not got_bolle:
                w_now = (get_now_dk() - st.session_state.arrival_times[name]["start"]).seconds // 60
                ca, cb, cc = st.columns([3, 2, 1])
                ca.info(f"⏱️ In queue: **{w_now} min** so far…")
                with cb:
                    if st.button("🛍️ Got it!", type="primary", use_container_width=True, key="strip_got"):
                        st.session_state.arrival_times[name]["wait"] = max(1, w_now)
                        st.rerun()
                with cc:
                    if st.button("✖", use_container_width=True, key="strip_close2"):
                        del st.session_state.arrival_times[name]
                        st.session_state.selected_bakery = None
                        st.rerun()

            else:
                wait_val = st.session_state.arrival_times[name]["wait"] if got_bolle else 0
                ca, cb, cc = st.columns([2, 2, 1])
                with ca:
                    if st.button("🏁 Queue Again", use_container_width=True, key="strip_requeue"):
                        if name in st.session_state.arrival_times:
                            del st.session_state.arrival_times[name]
                        st.session_state.review_mode = None
                        st.session_state.arrival_times[name] = {"start": get_now_dk(), "wait": None}
                        st.rerun()
                with cb:
                    if st.button("🚀 Fast Review", use_container_width=True, key="strip_refast"):
                        if name in st.session_state.arrival_times:
                            del st.session_state.arrival_times[name]
                        st.session_state.review_mode = "instant"
                        st.rerun()
                with cc:
                    if st.button("✖", use_container_width=True, key="strip_cancel"):
                        if name in st.session_state.arrival_times:
                            del st.session_state.arrival_times[name]
                        st.session_state.review_mode = None
                        st.session_state.selected_bakery = None
                        st.rerun()

                # ── Nickname gate ──────────────────────────────────────────
                nickname = st.session_state.user_nickname.strip()
                if not nickname or nickname == "BunHunter":
                    st.warning("👋 Pick a nickname before submitting your review!")
                    new_nick = st.text_input("Your nickname", key="nickname_gate",
                                             placeholder="e.g. CreamPuffCarla")
                    if st.button("Set Nickname & Continue", key="set_nick_btn"):
                        if new_nick.strip():
                            st.session_state.user_nickname = new_nick.strip()
                            st.session_state.nickname_set = True
                            # Persist to localStorage
                            components.html(f"""
                            <script>localStorage.setItem('bq_nickname', '{new_nick.strip()}');</script>
                            """, height=0)
                            st.rerun()
                    st.stop()

                # ── Rate limit: soft block same bakery same day ────────────
                if not df_raw.empty:
                    already = df_raw[
                        (df_raw['User'] == nickname) &
                        (df_raw['Bakery Name'] == name) &
                        (df_raw['Date'] == today_str) &
                        (df_raw['Category'] == 'User')
                    ]
                    if not already.empty:
                        st.warning(
                            f"⚠️ You've already reviewed **{name}** today. "
                            "Submit another if you visited again!"
                        )

                # ── Review form ────────────────────────────────────────────
                st.markdown("#### ✍️ Your Review")
                with st.form("final_review", clear_on_submit=False):
                    st.markdown("**📸 Add a photo** *(optional)*")
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
                               get_now_dk().strftime("%Y-%m-%d"), "User", nickname,
                               float(t_r), float(t_p), int(b_data['Stock']),
                               get_now_dk().strftime("%H:%M"), "", str(t_c), int(wait_val)]
                        post_to_sheets(row)
                        if name in st.session_state.arrival_times:
                            del st.session_state.arrival_times[name]
                        st.session_state.review_mode = None
                        st.session_state.selected_bakery = None
                        st.cache_data.clear()
                        st.balloons()
                        # Badge unlock — only notify if badge count increased
                        old_count = len(compute_badges(
                            df_raw[df_raw['User'] == nickname]
                        ))
                        new_df    = load_data()
                        new_count = len(compute_badges(
                            new_df[new_df['User'] == nickname]
                        ))
                        if new_count > old_count:
                            st.toast("🎉 New badge unlocked!", icon="🏅")
                        st.rerun()

    # ── MAP ───────────────────────────────────
    if not filtered.empty:
        latest = (
            filtered.sort_values(['Bakery Name', 'Date', 'Time'])
            .groupby('Bakery Name').last().reset_index()
        )
    else:
        latest = pd.DataFrame()

    m = folium.Map(location=[55.6761, 12.5683], zoom_start=13, tiles="cartodbpositron")

    for _, r in (latest.dropna(subset=['lat', 'lon'])
                 if not latest.empty and 'lat' in latest.columns
                 else pd.DataFrame()).iterrows():
        if r['lat'] == 0 and r['lon'] == 0:
            continue
        sold_out = r['Stock'] <= 0
        is_bv    = r['Bakery Name'] == best_value_bakery
        color    = "red" if sold_out else ("darkgreen" if is_bv else "green")
        icon_sym = "times" if sold_out else ("star" if is_bv else "shopping-basket")
        stock_txt = "🚫 Sold out" if sold_out else f"✅ {int(r['Stock'])} left"

        avg_wait_txt = ""
        if not stats_df.empty and r['Bakery Name'] in stats_df['Bakery Name'].values:
            bk_row = stats_df[stats_df['Bakery Name'] == r['Bakery Name']].iloc[0]
            avg_wait_txt = f"⏳ ~{int(bk_row['avg_wait'])} min avg wait<br>"

        oh = str(r.get('Opening Hours', ''))
        hours_txt = f"🕐 {esc(oh)}<br>" if oh and oh.lower() not in ('', 'nan', '0') else ""

        # geo: URI lets iOS open Apple Maps, Android opens Google Maps
        directions_url = f"geo:{r['lat']},{r['lon']}?q={r['lat']},{r['lon']}"

        popup_html = (
            f"<div style='font-family:sans-serif;font-size:13px;min-width:180px'>"
            f"<b style='font-size:14px'>{esc(r['Bakery Name'])}</b><br>"
            f"{'<span style=\"color:#059669\">💚 Best Value</span><br>' if is_bv else ''}"
            f"{stock_txt}<br>"
            f"🍩 {esc(r['Fastelavnsbolle Type'])}<br>"
            f"💰 {int(r['Price'])} kr &nbsp; ⭐ {float(r['Rating']):.1f}<br>"
            f"{avg_wait_txt}{hours_txt}"
            f"<a href='{directions_url}' "
            f"style='display:inline-block;margin-top:6px;background:#ff7e00;color:white;"
            f"padding:4px 10px;border-radius:8px;text-decoration:none;font-size:12px'>"
            f"🗺 Directions</a>"
            f"</div>"
        )
        folium.Marker(
            [r['lat'], r['lon']],
            tooltip=r['Bakery Name'],
            popup=folium.Popup(popup_html, max_width=240),
            icon=folium.Icon(color=color, icon=icon_sym, prefix='fa'),
        ).add_to(m)

    res = st_folium(m, width="100%", height=480, key="main_map")
    if res.get("last_object_clicked_tooltip"):
        clicked = res["last_object_clicked_tooltip"]
        if st.session_state.selected_bakery != clicked:
            st.session_state.selected_bakery = clicked
            st.rerun()

    col_ref, col_sug = st.columns([1, 1])
    with col_ref:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col_sug:
        with st.popover("➕ Suggest a Bakery", use_container_width=True):
            with st.form("suggest_bakery"):
                sug_name    = st.text_input("Bakery name")
                sug_address = st.text_input("Address")
                sug_note    = st.text_area("Anything else we should know?", height=80)
                if st.form_submit_button("Send Suggestion"):
                    if sug_name.strip():
                        post_to_sheets([
                            sug_name, "", "", sug_address, 0, 0,
                            get_now_dk().strftime("%Y-%m-%d"), "Suggestion",
                            st.session_state.user_nickname, 0, 0, 0,
                            get_now_dk().strftime("%H:%M"), "", sug_note, 0
                        ])
                        st.toast("Thanks! We'll look into adding them 🥐", icon="✅")

    # ── Full panel (below map) — stats, wish list, merchant form ──────────
    if st.session_state.selected_bakery:
        name = st.session_state.selected_bakery
        b_rows = df_raw[df_raw['Bakery Name'] == name]
        if not b_rows.empty:
            b_data        = b_rows.iloc[-1]
            is_merchant   = st.session_state.merchant_bakery == name
            is_best_value = best_value_bakery == name
            on_wish_list  = name in st.session_state.wish_list

            st.divider()
            title_extra = ""
            if is_best_value: title_extra += ' <span class="badge badge-best">💚 Best Value</span>'
            if is_merchant:   title_extra += ' <span class="badge">🧑‍🍳 YOUR SHOP</span>'
            st.markdown(f"#### 📍 {esc(name)} {title_extra}", unsafe_allow_html=True)

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

            wl_label = "💛 Remove from Wish List" if on_wish_list else "🤍 Add to Wish List"
            if st.button(wl_label, key="wl_toggle"):
                if on_wish_list:
                    st.session_state.wish_list.remove(name)
                else:
                    st.session_state.wish_list.append(name)
                st.rerun()

            st.divider()

            if is_merchant:
                st.subheader("🧑‍🍳 Update Your Shop")
                with st.form("merchant_update_map"):
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
                        st.toast("📡 Broadcast sent!", icon="✅")
                        st.rerun()

# ══════════════════════════════════════════════
# TAB: STREAM
# ══════════════════════════════════════════════
with t_stream:
    st.subheader("🧵 Live Feed")

    if st.session_state.user_filter:
        st.info(f"Showing posts by **@{esc(st.session_state.user_filter)}**")
        if st.button("✖ Clear Filter"):
            st.session_state.user_filter = None
            st.rerun()

    if not df_raw.empty:
        s_df = df_raw[df_raw['Category'].isin(['User', 'Merchant'])].sort_values(
            by=["Date", "Time"], ascending=False
        )
        # User filter applies only to user posts; merchant updates always show unless
        # the filter is set — in which case hide merchant posts too for clarity
        if st.session_state.user_filter:
            s_df = s_df[
                (s_df['Category'] == 'User') &
                (s_df['User'] == st.session_state.user_filter)
            ]

        if s_df.empty:
            st.info("No reviews yet — be the first!")
        else:
            for _, r in s_df.iterrows():
                is_bv      = r['Bakery Name'] == best_value_bakery
                bv_tag     = '<span class="badge badge-best">💚 Best Value</span>' if is_bv else ''
                photo_url  = str(r.get('Photo URL', ''))
                is_merch   = r['Category'] == 'Merchant'

                if is_merch:
                    st.markdown(f"""
                    <div class="review-card" style="border-color:#ffb347;background:#fff8f2;">
                      <div class="meta">📍 <b>{esc(r['Bakery Name'])}</b> {bv_tag} &nbsp;·&nbsp;
                           🧑‍🍳 <b>Merchant Update</b> &nbsp;·&nbsp; {esc(r['Date'])} {esc(r['Time'])}</div>
                      <div>🍩 {esc(r['Fastelavnsbolle Type'])} &nbsp;|&nbsp;
                           💰 {int(float(r['Price']))} kr &nbsp;|&nbsp;
                           📦 {int(float(r['Stock']))} in stock</div>
                      {'<div class="comment">📣 ' + esc(r['Comment']) + '</div>' if r['Comment'] else ''}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    share_js = share_text(r['Bakery Name'], float(r['Rating']))
                    st.markdown(f"""
                    <div class="review-card">
                      <div class="meta">📍 <b>{esc(r['Bakery Name'])}</b> {bv_tag} &nbsp;·&nbsp;
                           👤 @{esc(r['User'])} &nbsp;·&nbsp; {esc(r['Date'])} {esc(r['Time'])}</div>
                      <div class="stars">{stars(float(r['Rating']))} &nbsp; <b>{float(r['Rating']):.1f}</b>
                           &nbsp;|&nbsp; ⏳ {int(float(r.get('Wait Time', 0)))} min wait
                           &nbsp;|&nbsp; 💰 {int(float(r['Price']))} kr</div>
                      <div>🍩 {esc(r['Fastelavnsbolle Type'])}</div>
                      {'<div class="comment">' + esc(r['Comment']) + '</div>' if r['Comment'] else ''}
                      <div style="margin-top:8px">
                        <button onclick="navigator.clipboard.writeText('{share_js}').then(()=>alert('Copied!'))"
                          style="background:none;border:1px solid #ffb347;color:#b84a00;padding:3px 10px;
                                 border-radius:8px;font-size:0.78rem;cursor:pointer">📤 Share</button>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if photo_url.startswith('http'):
                        st.image(photo_url, use_container_width=True)
    else:
        st.info("No data yet.")

# ══════════════════════════════════════════════
# TAB: RANKINGS
# ══════════════════════════════════════════════
with t_top:
    st.subheader("🏆 Rankings")

    if not stats_df.empty:
        if best_value_bakery:
            bv_row = stats_df[stats_df['Bakery Name'] == best_value_bakery].iloc[0]
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#d4f7e0,#a8f0c8);border-radius:16px;
                        padding:20px;margin-bottom:20px;border:2px solid #38f9d7;">
              <div style="font-family:'Syne',sans-serif;font-size:1.3rem;color:#064e3b">💚 Best Value Bakery Award</div>
              <div style="font-size:1.6rem;font-weight:800;color:#065f46;margin:6px 0">{esc(best_value_bakery)}</div>
              <div style="color:#047857">⭐ {bv_row['avg_rating']:.2f} rating &nbsp;·&nbsp;
                   💰 {int(bv_row['avg_price'])} kr avg &nbsp;·&nbsp; {int(bv_row['review_count'])} reviews</div>
            </div>
            """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🥐 Bakeries by Rating**")
            for _, row in stats_df.head(10).iterrows():
                is_bv = row['Bakery Name'] == best_value_bakery
                st.markdown(
                    f"**{esc(row['Bakery Name'])}**{'💚' if is_bv else ''} — "
                    f"{stars(row['avg_rating'])} ({row['avg_rating']:.1f}, {int(row['review_count'])} reviews)"
                )
            st.markdown("---")
            st.markdown("**🍩 Top Flavors**")
            flavor_df = (
                df_raw[df_raw['Rating'] > 0]
                .groupby('Fastelavnsbolle Type')['Rating']
                .agg(['mean', 'count']).sort_values('mean', ascending=False).reset_index()
            )
            for _, row in flavor_df.head(8).iterrows():
                st.markdown(
                    f"**{esc(row['Fastelavnsbolle Type'])}** — "
                    f"{stars(row['mean'])} ({row['mean']:.1f}, {int(row['count'])} reviews)"
                )

        with c2:
            st.markdown("**💰 Best Value Scores**")
            for _, row in stats_df.sort_values('value_score', ascending=False).head(8).iterrows():
                st.markdown(
                    f"**{esc(row['Bakery Name'])}** — score {row['value_score']:.2f} "
                    f"(⭐{row['avg_rating']:.1f} / {int(row['avg_price'])}kr)"
                )

        st.divider()
        st.markdown("**👑 Top Hunters**")
        u_counts = (
            df_raw[df_raw['Category'] == 'User']['User']
            .value_counts().reset_index()
        )
        u_counts.columns = ['User', 'count']
        for i, row in u_counts.head(10).iterrows():
            user_revs   = df_raw[df_raw['User'] == row['User']]
            badges_html = "".join(compute_badges(user_revs))
            col_a, col_b = st.columns([5, 1])
            col_a.markdown(
                f"**@{esc(row['User'])}** — {int(row['count'])} reviews<br>{badges_html}",
                unsafe_allow_html=True
            )
            if col_b.button("View", key=f"u_{i}"):
                st.session_state.user_filter = row['User']
                st.rerun()

    # Inline reviews when View is clicked
    if st.session_state.user_filter and not df_raw.empty:
        st.divider()
        st.markdown(f"#### 👤 Reviews by @{esc(st.session_state.user_filter)}")
        if st.button("✖ Clear", key="rankings_clear_filter"):
            st.session_state.user_filter = None
            st.rerun()
        user_df = df_raw[
            (df_raw['User'] == st.session_state.user_filter) &
            (df_raw['Category'] == 'User')
        ].sort_values(by=["Date", "Time"], ascending=False)
        if user_df.empty:
            st.info("No reviews yet.")
        else:
            for _, r in user_df.iterrows():
                is_bv    = r['Bakery Name'] == best_value_bakery
                bv_tag   = '<span class="badge badge-best">💚 Best Value</span>' if is_bv else ''
                photo_url = str(r.get('Photo URL', ''))
                st.markdown(f"""
                <div class="review-card">
                  <div class="meta">📍 <b>{esc(r['Bakery Name'])}</b> {bv_tag}
                       &nbsp;·&nbsp; {esc(r['Date'])} {esc(r['Time'])}</div>
                  <div class="stars">{stars(float(r['Rating']))} &nbsp; <b>{float(r['Rating']):.1f}</b>
                       &nbsp;|&nbsp; ⏳ {int(float(r.get('Wait Time', 0)))} min wait
                       &nbsp;|&nbsp; 💰 {int(float(r['Price']))} kr</div>
                  <div>🍩 {esc(r['Fastelavnsbolle Type'])}</div>
                  {'<div class="comment">' + esc(r['Comment']) + '</div>' if r['Comment'] else ''}
                </div>
                """, unsafe_allow_html=True)
                if photo_url.startswith('http'):
                    st.image(photo_url, use_container_width=True)
    elif stats_df.empty:
        st.info("No reviews yet. Start hunting!")

# ══════════════════════════════════════════════
# TAB: WISH LIST
# ══════════════════════════════════════════════
with t_wishlist:
    st.subheader("💛 Your Wish List")
    st.caption("Tap 🤍 Add to Wish List on any bakery to save it here.")

    if not st.session_state.wish_list:
        st.info("Your wish list is empty. Tap a pin on the map and hit 🤍 Add to Wish List!")
    else:
        for bname in st.session_state.wish_list:
            with st.container(border=True):
                col_n, col_r, col_x = st.columns([4, 2, 1])
                col_n.markdown(f"**{esc(bname)}**")
                if not df_raw.empty:
                    b_rows = df_raw[df_raw['Bakery Name'] == bname]
                    if not b_rows.empty:
                        last   = b_rows.iloc[-1]
                        status = "🟢 In Stock" if last['Stock'] > 0 else "🔴 Sold Out"
                        col_r.markdown(status)
                if col_x.button("✖", key=f"wl_rm_{bname}"):
                    st.session_state.wish_list.remove(bname)
                    st.rerun()

# ══════════════════════════════════════════════
# TAB: DISCOUNTS
# ══════════════════════════════════════════════
with t_discounts:
    st.subheader("🏷️ BolleQuest Deals")

    # ── Coupon screen: full-screen view for showing at the counter ─────────
    if st.session_state.show_coupon:
        bakery = st.session_state.show_coupon
        d_row  = disc_df[disc_df['Bakery Name'] == bakery]
        if not d_row.empty:
            d = d_row.iloc[-1]
            pct  = int(float(d['Discount Pct']))
            desc = esc(d['Description'])
            # Rotating code: changes every 5 minutes so screenshots can't be reused
            code_seed = int(get_now_dk().timestamp() // 300)
            code = hashlib.sha256(f"{bakery}{code_seed}".encode()).hexdigest()[:6].upper()
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#1a0a00,#3d1a00);color:#ffb347;
                        border-radius:20px;padding:40px 28px;text-align:center;margin-bottom:20px">
              <div style="font-size:1rem;color:#c8895a;margin-bottom:4px">🏷️ BolleQuest Exclusive Deal</div>
              <div style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
                          margin:10px 0">{esc(bakery)}</div>
              <div style="font-size:4rem;font-weight:900;color:#ffb347;
                          line-height:1.1">{pct}% OFF</div>
              <div style="color:#ffd580;font-size:1rem;margin:10px 0">{desc}</div>
              <div style="background:#fff8f2;color:#3d1a00;border-radius:12px;
                          padding:12px 20px;margin-top:20px;display:inline-block">
                <div style="font-size:0.75rem;color:#888;margin-bottom:4px">SHOW THIS CODE AT THE COUNTER</div>
                <div style="font-family:monospace;font-size:2rem;font-weight:800;
                            letter-spacing:6px">{code}</div>
                <div style="font-size:0.7rem;color:#aaa;margin-top:4px">Refreshes every 5 min · @{esc(st.session_state.user_nickname)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("← Back to Deals", use_container_width=True):
                st.session_state.show_coupon = None
                st.rerun()
        st.stop()

    # ── Deals list ─────────────────────────────────────────────────────────
    active_deals = disc_df[disc_df['Active'] == '1']
    if active_deals.empty:
        st.info("No deals yet — check back soon! Bakeries can add deals in their merchant settings.")
    else:
        for _, d in active_deals.iterrows():
            pct  = int(float(d['Discount Pct']))
            desc = esc(d['Description'])
            until = esc(d['Valid Until'])
            bname = esc(d['Bakery Name'])
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.markdown(f"""
                <div style="background:#fff8f2;border:2px solid #ffb347;border-radius:14px;
                            padding:16px 18px;margin-bottom:10px">
                  <div style="font-family:'Syne',sans-serif;font-size:1.4rem;color:#b84a00;
                               font-weight:800">{pct}% OFF</div>
                  <div style="font-weight:700;font-size:1rem">{bname}</div>
                  <div style="color:#666;font-size:0.9rem">{desc}</div>
                  {'<div style="color:#aaa;font-size:0.78rem;margin-top:4px">Valid until ' + until + '</div>' if until and until != 'nan' else ''}
                </div>
                """, unsafe_allow_html=True)
            with col_b:
                if st.button("Show", key=f"coup_{d['Bakery Name']}", use_container_width=True,
                             type="primary"):
                    st.session_state.show_coupon = d['Bakery Name']
                    st.rerun()

# ══════════════════════════════════════════════
# TAB: SETTINGS
# ══════════════════════════════════════════════
with t_settings:
    st.subheader("⚙️ Settings")

    new_nick = st.text_input(
        "Your Hunter Nickname 🎯",
        value=st.session_state.user_nickname,
        placeholder="e.g. CreamPuffCarla"
    )
    if new_nick != st.session_state.user_nickname:
        st.session_state.user_nickname = new_nick
        components.html(
            f"<script>localStorage.setItem('bq_nickname','{html.escape(new_nick)}');</script>",
            height=0
        )

    if not df_raw.empty:
        my_revs   = df_raw[df_raw['User'] == st.session_state.user_nickname]
        my_badges = compute_badges(my_revs)
        if my_badges:
            st.markdown("**Your Badges:**")
            st.markdown(" ".join(my_badges), unsafe_allow_html=True)
        else:
            st.info("No badges yet — submit your first review to earn one!")

    st.divider()
    st.markdown("**🧑‍🍳 Merchant Access**")

    if st.session_state.merchant_bakery:
        name = st.session_state.merchant_bakery
        st.success(f"✅ Logged in as: **{esc(name)}**")

        b_rows = df_raw[df_raw['Bakery Name'] == name]
        if not b_rows.empty:
            b_data = b_rows.iloc[-1]

            tab_update, tab_discount = st.tabs(["📡 Broadcast Update", "🏷️ Manage Deal"])

            with tab_update:
                with st.form("merchant_update_settings"):
                    new_stock  = st.number_input("Current Stock", 0, 1000, int(b_data['Stock']))
                    new_flavor = st.text_input("Today's Featured Flavor", value=str(b_data['Fastelavnsbolle Type']))
                    new_price  = st.number_input("Price (DKK)", 0, 200, int(b_data['Price']))
                    new_hours  = st.text_input("Opening Hours (e.g. Mon–Fri 7–18, Sat 8–15)",
                                               value=str(b_data.get('Opening Hours', '')))
                    m_comm     = st.text_area("Merchant Note (e.g. 'Next batch at 2pm!')", value="")
                    if st.form_submit_button("📡 Broadcast Update", use_container_width=True, type="primary"):
                        row = [name, new_flavor, "", str(b_data['Address']),
                               float(b_data['lat']), float(b_data['lon']),
                               get_now_dk().strftime("%Y-%m-%d"), "Merchant", name,
                               5.0, new_price, new_stock,
                               get_now_dk().strftime("%H:%M"), new_hours, m_comm, 0]
                        post_to_sheets(row)
                        st.cache_data.clear()
                        st.toast("📡 Broadcast sent!", icon="✅")
                        st.rerun()

            with tab_discount:
                existing = disc_df[disc_df['Bakery Name'] == name]
                ex = existing.iloc[-1] if not existing.empty else None
                with st.form("merchant_discount"):
                    st.markdown("Set a discount that customers can show at your counter.")
                    d_pct   = st.number_input("Discount %", 0, 100,
                                              int(float(ex['Discount Pct'])) if ex is not None else 10)
                    d_desc  = st.text_input("Deal description", value=str(ex['Description']) if ex is not None else "",
                                            placeholder="e.g. Free coffee with any bolle!")
                    d_until = st.text_input("Valid until (optional)", value=str(ex['Valid Until']) if ex is not None else "",
                                            placeholder="e.g. 4 March 2026")
                    d_active = st.checkbox("Deal is active", value=(ex is not None and str(ex['Active']) == '1'))
                    if st.form_submit_button("💾 Save Deal", use_container_width=True, type="primary"):
                        save_discount(name, d_pct, d_desc, d_until)
                        ws = get_discounts_worksheet()
                        data = ws.get_all_values()
                        for i, row in enumerate(data[1:], start=2):
                            if row and row[0] == name:
                                ws.update(f"E{i}", [["1" if d_active else "0"]])
                                break
                        st.cache_data.clear()
                        st.toast("💾 Deal saved!", icon="✅")
                        st.rerun()

        if st.button("🚪 Log Out"):
            st.session_state.merchant_bakery = None
            st.rerun()
    else:
        st.markdown("**Log in with your key:**")
        k_in = st.text_input("Bakery Secret Key", type="password")
        if st.button("🔑 Unlock Merchant Tools"):
            if not df_raw.empty and k_in:
                hashed = hash_key(k_in)
                match  = df_raw[df_raw['Bakery Key'] == hashed]
                if not match.empty:
                    st.session_state.merchant_bakery = match['Bakery Name'].iloc[0]
                    st.rerun()
                else:
                    st.error("Key not recognised.")

        st.divider()
        with st.expander("🏪 Register your bakery"):
            st.markdown(
                "Don't have a key yet? Register here — your bakery will appear on the map "
                "once we've verified your location (usually within 24 hours)."
            )
            with st.form("bakery_register"):
                reg_name    = st.text_input("Bakery name")
                reg_address = st.text_input("Address")
                reg_flavor  = st.text_input("Your signature bolle flavor", placeholder="e.g. Hindbær/Vanilje")
                reg_price   = st.number_input("Price (DKK)", 10, 200, 45)
                reg_hours   = st.text_input("Opening hours", placeholder="Mon–Fri 7–18, Sat 8–15")
                reg_pass    = st.text_input("Choose a login password", type="password")
                reg_pass2   = st.text_input("Confirm password", type="password")
                if st.form_submit_button("📝 Register", use_container_width=True, type="primary"):
                    if not reg_name.strip():
                        st.error("Please enter your bakery name.")
                    elif not reg_pass.strip():
                        st.error("Please choose a password.")
                    elif reg_pass != reg_pass2:
                        st.error("Passwords don't match.")
                    elif not df_raw.empty and (df_raw['Bakery Name'] == reg_name.strip()).any():
                        st.error("That bakery name is already registered. Contact us if this is your bakery.")
                    else:
                        hashed_new = hash_key(reg_pass)
                        row = [reg_name.strip(), reg_flavor, "", reg_address.strip(),
                               0, 0,
                               get_now_dk().strftime("%Y-%m-%d"), "Registration",
                               reg_name.strip(), 0, reg_price, 0,
                               get_now_dk().strftime("%H:%M"), reg_hours,
                               "Awaiting map placement", hashed_new]
                        post_to_sheets(row)
                        st.cache_data.clear()
                        st.success(
                            f"✅ **{reg_name.strip()}** registered! You can log in with your password now. "
                            "We'll add you to the map shortly."
                        )
                        # Auto-log them in
                        st.session_state.merchant_bakery = reg_name.strip()
                        st.rerun()

# ══════════════════════════════════════════════
# TAB: HELP
# ══════════════════════════════════════════════
with t_help:
    st.markdown("""
### 🥐 How to use BolleQuest

**Finding bolles**
- Green pins = in stock · Red = sold out · Dark green ★ = Best Value bakery
- Use 🎛️ Filters to narrow by rating, price, or search by name/flavor
- Tap any pin to see the popup, then scroll down for stats and review options

**Reviewing**
- Tap a pin → **Join the Queue** (we time your wait) or **Fast Review** (already eaten?)
- Add a photo from your phone camera
- Your review updates the live feed and rankings instantly

**Sharing**
- Tap 📤 Share on any review card to copy a shareable message to your clipboard

**Wish List**
- Tap 🤍 Add to Wish List on any bakery to track it for later

**Badges** 🏅
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

**Add to Home Screen 📱**
On iPhone: tap Share ↑ → "Add to Home Screen". On Android: tap ⋮ menu → "Add to Home Screen" *(may be under "More options")*.

**Discounts 🏷️**
Check the Discounts tab for exclusive deals. Tap "Show" to display your coupon code at the counter — codes rotate every 5 minutes so they can't be reused from a screenshot.

**For bakeries 🧑‍🍳**
- Already have a key? Enter it in ⚙️ Settings → Merchant Access.
- New bakery? Use the "Register your bakery" form — you choose your own password and get immediate access. We'll add you to the map within 24 hours.
- Once logged in, use **Broadcast Update** to update stock, price and flavor, and **Manage Deal** to set a discount for BolleQuest users.
    """)
