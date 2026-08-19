import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium
from shapely.geometry import shape

from gee_auth import init_gee
from data_loader import load_data
from ndvi_analysis import calculate_ndvi_time_series

st.set_page_config(layout="wide")
st.title("🌱 RDOŚ Monitoring - Natura 2000")

if init_gee():
    st.sidebar.header("Panel sterowania")

    data_plb = load_data("PLB.geojson")
    data_plh = load_data("PLH.geojson")

    if data_plb and data_plh:
        typ = st.sidebar.radio("Wybierz kategorię:", ("PLB (Ptaki)", "PLH (Siedliska)"))
        active_data = data_plb if "PLB" in typ else data_plh

        names = [
            f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") or "Bez nazwy"
            for f in active_data["features"]
        ]
        wybrany = st.sidebar.selectbox("Wybierz obszar:", sorted(list(set(names))))

        # Resetujemy zapamiętany wykres w sesji, jeśli użytkownik zmienił obszar
        if "last_wybrany" not in st.session_state or st.session_state["last_wybrany"] != wybrany:
            st.session_state["last_wybrany"] = wybrany
            st.session_state["df_ts"] = None

        feat = next(
            f for f in active_data["features"]
            if (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany
        )
        geom = shape(feat["geometry"])

        # Generowanie mapy Folium
        m = folium.Map(location=[geom.centroid.y, geom.centroid.x], zoom_start=11)
        kolor = 'blue' if "PLB" in typ else 'green'
        folium.GeoJson(
            feat,
            style_function=lambda x: {'color': kolor, 'fillOpacity': 0.3, 'weight': 3}
        ).add_to(m)

        st.sidebar.success(f"Wybrano: {wybrany}")

        # --- SEKCJA ANALIZY CZASOWEJ NDVI ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("📈 Szereg czasowy NDVI")

        start_date = st.sidebar.date_input("Data początkowa", value=pd.to_datetime("2025-01-01"))
        end_date = st.sidebar.date_input("Data końcowa", value=pd.to_datetime("2026-08-19"))

        if st.sidebar.button("Generuj wykres zmian NDVI"):
            with st.spinner("Pobieranie szeregu czasowego ze Sentinel-2..."):
                st.session_state["df_ts"] = calculate_ndvi_time_series(feat, start_date, end_date)

        # Wyświetlenie wykresu, jeśli dane istnieją w sesji
        if st.session_state.get("df_ts") is not None and not st.session_state["df_ts"].empty:
            st.subheader(f"Dynamika wskaźnika NDVI dla obszaru: {wybrany}")
            st.line_chart(st.session_state["df_ts"])
        elif st.session_state.get("df_ts") is not None and st.session_state["df_ts"].empty:
            st.warning("Brak danych satelitarnych w wybranym przedziale. Spróbuj rozszerzyć zakres dat.")

        # Wyświetlenie mapy
        st_folium(m, width=1100, height=500)
    else:
        st.error("Upewnij się, że pliki PLB.geojson i PLH.geojson znajdują się w folderze głównym projektu!")