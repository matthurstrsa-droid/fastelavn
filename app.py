# --- THE PULSE COUNTER (Top of Feed) ---
def render_pulse_header(df):
    try:
        # Filter for reports in the last 24 hours
        # (Simplified check: count rows from 'Today')
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_activity = df[df['Date'] == today_str]
        total_spotted = len(today_activity)
        avg_rating = today_activity['Rating'].mean() if not today_activity.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Buns Spotted", f"{total_spotted} today")
        c2.metric("City Avg", f"{avg_rating:.1f} ⭐")
        c3.metric("Live Bakeries", f"{df[df['Stock'] > 0]['Bakery Name'].nunique()} open")
        st.divider()
    except:
        pass

# --- 1. THE TWITTER-STYLE FEED TAB ---
with t_buns:
    render_pulse_header(df_clean)
    
    st.subheader("🧵 The Bun Stream")
    
    # Sort: Absolute latest on top
    timeline = filtered.sort_values(by=['Date', 'Last Updated'], ascending=False)
    
    if timeline.empty:
        st.info("The stream is quiet... Go be the first to report! 🥯")
    else:
        for i, (idx, row) in enumerate(timeline.iterrows()):
            with st.container(border=True):
                # Header: User Handle & Relative Time
                col_u, col_t = st.columns([3, 1])
                with col_u:
                    # Create a "Handle" from the user name or bakery name
                    handle = row['User'].replace(" ", "").lower() if row['User'] else "guest"
                    st.markdown(f"**{row['Bakery Name']}** <span style='color:gray; font-size:0.8em;'>@{handle}</span>", unsafe_allow_html=True)
                
                with col_t:
                    try:
                        report_t = datetime.strptime(row['Last Updated'], "%H:%M")
                        now_t = datetime.strptime(get_now_dk(), "%H:%M")
                        diff_min = int((now_t - report_t).total_seconds() / 60)
                        
                        if 0 <= diff_min < 60:
                            st.caption(f"• {diff_min}m")
                        else:
                            st.caption(f"• {row['Last Updated']}")
                    except:
                        st.caption(f"• {row['Last Updated']}")

                # The "Tweet" Content
                st.markdown(f"**Flavor:** {row['Fastelavnsbolle Type']}")
                
                # Star Rating Bar
                stars = "★" * int(round(row['Rating'])) + "☆" * (5 - int(round(row['Rating'])))
                st.markdown(f"<span style='color:#FFB800;'>{stars}</span>", unsafe_allow_html=True)

                # The "X-style" Comment
                if 'Comment' in row and row['Comment']:
                    st.markdown(f" {row['Comment']}")
                
                # Action Bar
                ca, cb, cc = st.columns([1, 1, 3])
                with ca:
                    if st.button("📍", key=f"fmap_{i}", help="Show on map"):
                        st.session_state.selected_bakery = row['Bakery Name']
                        st.rerun()
                with cb:
                    st.button("❤️", key=f"like_{i}")
                with cc:
                    # Status Indicator
                    if row['Stock'] <= 0:
                        st.markdown("<span style='color:red; font-size:0.8em;'>🚫 SOLD OUT</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='color:green; font-size:0.8em;'>✅ IN STOCK</span>", unsafe_allow_html=True)

# --- 2. UPDATE THE "POST" BUTTON IN POPOVER ---
# (Inside your Action Center logic)
with st.popover("🚀 Post to Stream", use_container_width=True):
    tweet_content = st.text_area("What's the status?", placeholder="Flavor, queue length, or general vibes...", max_chars=280)
    tweet_flavor = st.text_input("Specific Flavor", value=row['Fastelavnsbolle Type'])
    tweet_rating = st.select_slider("Rate this bun", options=[1, 2, 3, 4, 5], value=4)
    
    if st.button("Post 🚀", use_container_width=True, type="primary"):
        ws = get_worksheet()
        ws.append_row([
            name, tweet_flavor, "", row['Address'], row['lat'], row['lon'],
            datetime.now().strftime("%Y-%m-%d"), "User Report", "Guest",
            tweet_rating, 45, stock, get_now_dk(), row.get('Bakery Key', ''), tweet_content
        ], value_input_option='USER_ENTERED')
        st.toast("Posted to the Stream!")
        st.cache_data.clear(); time.sleep(1); st.rerun()
