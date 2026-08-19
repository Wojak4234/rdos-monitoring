import ee
import streamlit as st

@st.cache_resource
def init_gee():
    try:
        credentials = ee.ServiceAccountCredentials(
            st.secrets["gcp_service_account"]["client_email"],
            key_data=st.secrets["gcp_service_account"]["private_key"]
        )
        ee.Initialize(credentials)
        return True
    except Exception as e:
        st.error(f"Błąd GEE: {e}")
        return False