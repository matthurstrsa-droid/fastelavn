import streamlit as st
import pandas as pd
from datetime import datetime

# App Config
st.set_page_config(page_title="Fastelavns Ratings 2026", page_icon="🥐")

st.title("🥐 Fastelavnsbolle Critic 2026")
st.subheader("Rate your way through Denmark's best buns.")

# 1. Input Section
with st.form("rating_form", clear_on_submit=True):
    bakery = st.selectbox("Which Bakery?", [
        "Andersen Bakery", "Hart Bageri", "Juno the Bakery", 
        "Bageriet Brød", "La Glace", "Sct. Peders Bageri", "Other"
    ])
    
    flavor = st.text_input("Flavor (e.g., Yuzu/Matcha, Classic Custard)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        dough = st.slider("Dough/Pastry", 1, 10, 5)
    with col2:
        filling = st.slider("Filling/Cream", 1, 10, 5)
    with col3:
        look = st.slider("Aesthetic", 1, 10, 5)
        
    comment = st.text_area("Final Verdict")
    submit = st.form_submit_button("Save Rating")

# 2. Data Handling (Using Session State for this demo)
if "ratings" not in st.session_state:
    st.session_state.ratings = []

if submit:
    new_rating = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Bakery": bakery,
        "Flavor": flavor,
        "Total Score": round((dough + filling + look) / 3, 1),
        "Verdict": comment
    }
    st.session_state.ratings.append(new_rating)
    st.success(f"Rating for {bakery} saved!")

# 3. Display Leaderboard
if st.session_state.ratings:
    df = pd.DataFrame(st.session_state.ratings)
    st.write("### Your Bun Leaderboard")
    st.dataframe(df.sort_values(by="Total Score", ascending=False), use_container_width=True)
else:
    st.info("No buns rated yet. Go eat some pastry!")