import streamlit as st

st.set_page_config(page_title="Basic Test App") # Optional: Give the browser tab a title

st.title("App is Loading!") # Add a title visible on the page
st.write("Hello World")    # The main content

st.success("If you see this, the basic Streamlit app ran successfully.") # Confirmation message
