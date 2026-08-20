import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium
from shapely.geometry import shape

from gee_auth import init_gee
from data_loader import load_data
from satellite_analysis import calculate_index_time_series, get_atmospheric_layer

st.set_page_config(layout="wide")
st.title("🌱 RDOŚ Monitoring - Ekosystemy i Atmosfera")

if init_gee():
    st.sidebar.header("Panel sterowania")

    data_plb = load_data("PLB.geojson")
    data_plh = load_data("PLH.geojson")

    if data_plb and data_plh:
        modul = st.sidebar.radio("Wybierz moduł analizy:",
                                 ("Obszary Natura 2000 (Wskaźniki)", "Zanieczyszczenie powietrza (S5P)"))

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

                csv_data = st.session_state["df_ts"].to_csv().encode('utf-8')
                st.download_button(
                    label="📥 Pobierz dane wykresu do CSV",
                    data=csv_data,
                    file_name=f"analiza_{selected_index.split()[0]}_{wybrany}.csv",
                    mime="text/csv",
                )
            elif st.session_state.get("df_ts") is not None and st.session_state["df_ts"].empty:
                st.warning("Brak danych satelitarnych w wybranym przedziale. Spróbuj rozszerzyć zakres dat.")

            # MAGIA DZIEJE SIĘ TUTAJ: returned_objects=[] zapobiega crashom białego ekranu
            st_folium(m, width=1100, height=500, returned_objects=[])

        else:
            st.header("🏭 Monitoring jakości powietrza (Zachodniopomorskie)")
            st.markdown("Wybierz datę oraz parametr, aby sprawdzić obszary o podwyższonym stężeniu zanieczyszczeń.")

            col1, col2 = st.columns(2)
            with col1:
                selected_date = st.date_input("Wybierz datę zobrazowania:", value=pd.to_datetime("2026-08-15"))
            with col2:
                selected_param = st.selectbox(
                    "Wybierz badany gaz/parametr:",
                    ("NO2 (Dwutlenek azotu)", "SO2 (Dwutlenek siarki)", "CO (Tlenek węgla)", "Aerozole (Smog / Pyły)")
                )

            if st.button("Generuj mapę zanieczyszczeń"):
                with st.spinner(f"Pobieranie danych dla {selected_param}..."):
                    tile_url = get_atmospheric_layer(str(selected_date), selected_param)

                    if tile_url:
                        # Wycentrowanie na środek woj. zachodniopomorskiego
                        m_atm = folium.Map(location=[53.6, 15.6], zoom_start=8)

                        folium.TileLayer(
                            tiles=tile_url,
                            attr="Google Earth Engine - Sentinel-5P",
                            name=selected_param,
                            overlay=True,
                            control=True,
                            opacity=0.6
                        ).add_to(m_atm)

                        folium.LayerControl().add_to(m_atm)

                        st.success(f"Warstwa {selected_param} została wygenerowana dla województwa!")
                        # TUTAJ RÓWNIEŻ BLOKUJEMY CRASHE
                        st_folium(m_atm, width=1100, height=600, returned_objects=[])
                    else:
                        st.error("Brak danych satelitarnych dla tego dnia (satelita mógł nie wykonać pomiaru lub obszar był zakryty grubymi chmurami). Wybierz inną datę.")
    else:
        st.error("Upewnij się, że pliki PLB.geojson i PLH.geojson znajdują się w folderze głównym projektu!")