# --- Find this section in your Sidebar code and replace the flavor logic ---

b_rows = df_clean[df_clean['Bakery Name'] == chosen]

# 1. FIX: Filter out "Wishlist" from the dropdown options
raw_flavs = b_rows['Fastelavnsbolle Type'].unique()
flavs = sorted([
    str(f).strip() for f in raw_flavs 
    if f and str(f).strip() 
    and not str(f).isdigit() 
    and str(f).lower() != "wishlist"  # <-- This line removes 'Wishlist' from the list
])

# 2. FIX: Use a consistent key for the selectbox to prevent "weird" jumping
f_sel = st.selectbox(
    "Select existing flavor", 
    flavs + ["➕ New..."], 
    key=f"f_sel_dropdown_{chosen}" # More specific key
)

if f_sel == "➕ New...":
    f_name = st.text_input("New flavor name:", key=f"f_text_input_{chosen}")
else:
    f_name = f_sel
