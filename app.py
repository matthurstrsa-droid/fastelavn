# --- UPDATED ACTION CENTER LOGIC (REPLACING SECTION 6) ---

if st.session_state.selected_bakery:
    name = st.session_state.selected_bakery
    b_row = df_raw[df_raw['Bakery Name'] == name].iloc[0]
    is_m = st.session_state.merchant_bakery == name
    is_sold_out = int(b_row['Stock']) <= 0
    
    with st.popover(f"📍 {name} {'(Admin)' if is_m else ''}", use_container_width=True):
        if is_m:
            # MERCHANT ALWAYS HAS ACCESS
            st.subheader("🧑‍🍳 Merchant Update")
            st.write(f"Current Stock: {b_row['Stock']}")
            ns = st.number_input("Update Stock Level", 0, 500, int(b_row['Stock']))
            t_f = st.text_input("Current Flavor", value=b_row['Fastelavnsbolle Type'])
            img = st.file_uploader("Update Official Photo", type=['jpg','png','jpeg'])
            
            if st.button("Post Official Update ✅", type="primary", use_container_width=True):
                with st.spinner("Broadcasting..."):
                    i_url = cloudinary.uploader.upload(img)['secure_url'] if img else b_row['Photo URL']
                    ws = get_worksheet(); cell = ws.find(name)
                    ws.update_cell(cell.row, 2, t_f); ws.update_cell(cell.row, 3, i_url)
                    ws.update_cell(cell.row, 12, ns); ws.update_cell(cell.row, 13, get_now_dk())
                    
                    # Add to Stream
                    ws.append_row([str(name), str(t_f), str(i_url), str(b_row['Address']), float(b_row['lat']), float(b_row['lon']), 
                                  datetime.now().strftime("%Y-%m-%d"), "Merchant", str(name), 5.0, float(b_row['Price']), 
                                  int(ns), str(get_now_dk()), str(b_row.get('Bakery Key','')), "OFFICIAL: Stock refreshed!"], 
                                  value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.session_state.selected_bakery = None; st.rerun()
        
        elif is_sold_out:
            # USER VIEW WHEN SOLD OUT
            st.error(f"🚫 {name} is currently SOLD OUT.")
            st.write("Reviews are disabled until the bakery updates their stock. Check back soon!")
            if st.button("Close", use_container_width=True):
                st.session_state.selected_bakery = None; st.rerun()
                
        else:
            # USER VIEW WHEN IN STOCK
            st.subheader("🥐 Community Review")
            st.write(f"Verified Flavor: {b_row['Fastelavnsbolle Type']}")
            img = st.file_uploader("Upload Your Photo", type=['jpg','png','jpeg'])
            t_f = st.text_input("Confirm Flavor", value=b_row['Fastelavnsbolle Type'])
            t_c = st.text_area("Your Review", max_chars=280)
            r_opts = [round(x, 2) for x in np.arange(1, 5.25, 0.25).tolist()]
            t_r = st.select_slider("Rating", options=r_opts, value=4.0)
            
            if st.button("Post Review 🚀", use_container_width=True, type="primary"):
                with st.spinner("Posting..."):
                    i_url = cloudinary.uploader.upload(img)['secure_url'] if img else ""
                    get_worksheet().append_row([str(name), str(t_f), str(i_url), str(b_row['Address']), float(b_row['lat']), float(b_row['lon']), 
                                              datetime.now().strftime("%Y-%m-%d"), "User Report", str(st.session_state.user_nickname), float(t_r), 
                                              float(b_row['Price']), int(b_row['Stock']), str(get_now_dk()), "", str(t_c)], 
                                              value_input_option='USER_ENTERED')
                    st.cache_data.clear(); st.session_state.selected_bakery = None; st.rerun()
