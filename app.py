import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium
from shapely.geometry import shape
import geemap.foliumap as geemap

from gee_auth import init_gee
from data_loader import load_data
from satellite_analysis import calculate_index_time_series, get_atmospheric_no2_data

st.set_page_config(layout="wide")
st.title("🌱 RDOŚ Monitoring - Ekosystemy i Atmosfera")

if init_gee():
    st.sidebar.header("Panel sterowania")

    data_plb = load_data("PLB.geojson")
    data_plh = load_data("PLH.geojson")

    if data_plb and data_plh:
        # Wybór modułu głównego
        modul = st.sidebar.radio("Wybierz moduł analizy:",
                                 ("Obszary Natura 2000 (Wskaźniki)", "Zanieczyszczenie powietrza (NO2)"))

        if modul == "Obszary Natura 2000 (Wskaźniki)":
            typ = st.sidebar.radio("Wybierz kategorię:", ("PLB (Ptaki)", "PLH (Siedliska)"))
            active_data = data_plb if "PLB" in typ else data_plh

            names = [
                f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") or "Bez nazwy"
                for f in active_data["features"]
            ]
            wybrany = st.sidebar.selectbox("Wybierz obszar:", sorted(list(set(names))))

            if "last_wybrany" not in st.session_state or st.session_state["last_wybrany"] != wybrany:
                st.session_state["last_wybrany"] = wybrany
                st.session_state["df_ts"] = None

            feat = next(
                f for f in active_data["features"]
                if (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany
            )
            geom = shape(feat["geometry"])

            # Mapa główna
            m = folium.Map(location=[geom.centroid.y, geom.centroid.x], zoom_start=11)
            kolor = 'blue' if "PLB" in typ else 'green'
            folium.GeoJson(
                feat,
                style_function=lambda x: {'color': kolor, 'fillOpacity': 0.3, 'weight': 3}
            ).add_to(m)

            st.sidebar.success(f"Wybrano: {wybrany}")

            st.sidebar.markdown("---")
            st.sidebar.subheader("📈 Wybór wskaźnika satelitarnego")
            selected_index = st.sidebar.selectbox(
                "Wskaźnik:",
                ("NDVI (Wegetacja)", "NDWI (Woda / Mokradła)", "NDMI (Wilgotność roślin)")
            )

            start_date = st.sidebar.date_input("Data początkowa", value=pd.to_datetime("2025-01-01"))
            end_date = st.sidebar.date_input("Data końcowa", value=pd.to_datetime("2026-08-19"))

            if st.sidebar.button("Generuj wykres wskaźnika"):
                with st.spinner(f"Pobieranie szeregu czasowego ({selected_index}) ze Sentinel-2..."):
                    st.session_state["df_ts"] = calculate_index_time_series(feat, selected_index, start_date, end_date)

            if st.session_state.get("df_ts") is not None and not st.session_state["df_ts"].empty:
                st.subheader(f"Dynamika wskaźnika {selected_index} dla: {wybrany}")
                st.line_chart(st.session_state["df_ts"])

                # Przycisk eksportu do CSV
                csv_data = st.session_state["df_ts"].to_csv().encode('utf-8')
                st.download_button(
                    label="📥 Pobierz dane wykresu do CSV",
                    data=csv_data,
                    file_name=f"analiza_{selected_index.split()[0]}_{wybrany}.csv",
                    mime="text/csv",
                )
            elif st.session_state.get("df_ts") is not None and st.session_state["df_ts"].empty:
                st.warning("Brak danych satelitarnych w wybranym przedziale. Spróbuj rozszerzyć zakres dat.")

            st_folium(m, width=1100, height=500)

        else:
            # --- MODUŁ ZANIECZYSZCZEŃ (SENTINEL-5P / NO2) ---
            st.header("🏭 Monitoring jakości powietrza i gazów śladowych (Sentinel-5P)")
            st.markdown("Moduł prezentuje rozkład stężenia dwutlenku azotu ($NO_2$) w troposferze dla obszaru Polski.")

            s_date = st.date_input("Okres od:", value=pd.to_datetime("2026-06-01"))
            e_date = st.date_input("Okres do:", value=pd.to_datetime("2026-08-19"))

            if st.button("Generuj mapę zanieczyszczeń NO2"):
                with st.spinner("Przetwarzam dane atmosferyczne z chmury GEE..."):
                    no2_image = get_atmospheric_no2_data(s_date, e_date)

                    # Tworzenie interaktywnej mapy z geemap
                    m_atm = geemap.Map(center=[52.0, 19.0], zoom=6)

                    # Wizualizacja warstwy NO2 z paletą kolorów (od niebieskiego do czerwonego/wysokie zanieczyszczenie)
                    no2_viz = {
                        'min': 0,
                        'max': 0.0002,
                        'palette': ['black', 'blue', 'purple', 'cyan', 'green', 'yellow', 'red']
                    }
                    m_atm.addLayer(no2_image, no2_viz, 'Stężenie NO2')

                    st.success("Mapa stężenia dwutlenku azotu została wygenerowana!")
                    m_atm.to_streamlit(height=600)

                    st.info(
                        "💡 Najwyższe stężenia $NO_2$ z reguły korelują z dużymi aglomeracjami miejskimi, arteriami komunikacyjnymi o dużym natężeniu ruchu oraz okręgami przemysłowymi.")
    else:
        st.error("Upewnij się, że pliki PLB.geojson i PLH.geojson znajdują się w folderze głównym projektu!")