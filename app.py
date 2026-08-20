import streamlit as st
import folium
import pandas as pd
import json
import branca.colormap as cm
from streamlit_folium import st_folium
from shapely.geometry import shape

from gee_auth import init_gee
from data_loader import load_data
from satellite_analysis import (
    calculate_index_time_series,
    get_atmospheric_layer,
    get_available_dates,
    get_parameter_info,
    get_s2_water_dates,
    get_water_quality_layer,
    get_osm_data
)

st.set_page_config(layout="wide")
st.title("🌱 RDOŚ Monitoring - Ekosystemy i Atmosfera")

if init_gee():
    st.sidebar.header("Panel sterowania")

    data_plb = load_data("PLB.geojson")
    data_plh = load_data("PLH.geojson")

    if data_plb and data_plh:
        modul = st.sidebar.radio(
            "Wybierz moduł analizy:",
            (
                "Obszary Natura 2000 (Wskaźniki)",
                "Zanieczyszczenie powietrza (S5P)",
                "Jakość Wód (Chlorofil-a)",
                "Dane wektorowe (OSM)"
            )
        )

        # ---------------- MODUŁ 1: NATURA 2000 ----------------
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

            st_folium(m, width=1100, height=500, returned_objects=[])

        # ---------------- MODUŁ 2: POWIETRZE S5P ----------------
        elif modul == "Zanieczyszczenie powietrza (S5P)":
            st.header("🏭 Monitoring jakości powietrza (Zachodniopomorskie)")
            st.markdown("Krok 1: Wybierz parametr gazowy. Krok 2: Wybierz z listy jedną z dostępnych dat.")

            selected_param = st.selectbox(
                "Wybierz badany gaz/parametr:",
                ("NO2 (Dwutlenek azotu)", "SO2 (Dwutlenek siarki)", "CO (Tlenek węgla)", "Aerozole (Smog / Pyły)")
            )

            if "last_param" not in st.session_state or st.session_state["last_param"] != selected_param:
                st.session_state["last_param"] = selected_param
                st.session_state["available_dates"] = None

            if st.session_state["available_dates"] is None:
                with st.spinner("Przeszukuję archiwum GEE w poszukiwaniu dostępnych zdjęć..."):
                    try:
                        st.session_state["available_dates"] = get_available_dates(selected_param, days_back=90)
                    except Exception as e:
                        st.error(f"Wystąpił problem z połączeniem do serwerów Earth Engine: {e}")
                        st.session_state["available_dates"] = []

            dates = st.session_state["available_dates"]

            if dates:
                selected_date_str = st.selectbox("Wybierz datę zobrazowania:", dates)

                if st.button("Generuj mapę zanieczyszczeń"):
                    with st.spinner(f"Przetwarzanie mapy {selected_param} dla daty {selected_date_str}..."):
                        try:
                            tile_url, min_val, max_val = get_atmospheric_layer(selected_date_str, selected_param)

                            if tile_url:
                                m_atm = folium.Map(location=[53.6, 15.6], zoom_start=8)

                                folium.TileLayer(
                                    tiles=tile_url,
                                    attr="Google Earth Engine - Sentinel-5P",
                                    name=selected_param,
                                    overlay=True,
                                    control=True,
                                    opacity=0.6
                                ).add_to(m_atm)

                                colormap = cm.LinearColormap(
                                    colors=['yellow', 'orange', 'red', 'purple'],
                                    vmin=min_val,
                                    vmax=max_val
                                )
                                colormap.caption = f"Wartość stężenia ({selected_param.split()[0]})"
                                colormap.add_to(m_atm)

                                folium.LayerControl().add_to(m_atm)

                                st.success(
                                    f"Warstwa {selected_param} dla daty {selected_date_str} została wygenerowana!")
                                st_folium(m_atm, width=1100, height=600, returned_objects=[])

                                param_info = get_parameter_info(selected_param)
                                if param_info:
                                    with st.expander("ℹ️ Jak czytać ten wynik? (Opis i progi ostrzegawcze)"):
                                        st.markdown(f"**Co to jest?**<br>{param_info['opis']}", unsafe_allow_html=True)
                                        st.markdown(
                                            f"**Jak interpretować wartości na mapie?**<br>{param_info['normy']}",
                                            unsafe_allow_html=True)
                                        st.info(
                                            "Pamiętaj: Pomiary satelitarne (zbierane z całej pionowej kolumny atmosfery) nie zawsze pokrywają się 1 do 1 z odczytami stacji naziemnych.")

                            else:
                                st.error("Nie udało się pobrać warstwy (prawdopodobnie brak danych po filtracji).")
                        except Exception as e:
                            st.error(f"Wystąpił błąd silnika Earth Engine: {e}")
            else:
                st.warning(
                    "Niestety nie znaleziono żadnych zdjęć satelitarnych dla tego parametru w ciągu ostatnich 90 dni.")

        # ---------------- MODUŁ 3: JAKOŚĆ WÓD (NDCI) ----------------
        elif modul == "Jakość Wód (Chlorofil-a)":
            st.header("💧 Monitoring jakości wód (Odra i Zalew Szczeciński)")
            st.markdown(
                "Śledzenie zakwitów glonów i sinic przy użyciu satelity Sentinel-2 i wskaźnika NDCI. Ląd został automatycznie zamaskowany.")

            if "water_dates" not in st.session_state:
                with st.spinner("Pobieram listę dostępnych, bezchmurnych dni dla Zalewu Szczecińskiego..."):
                    try:
                        st.session_state["water_dates"] = get_s2_water_dates(days_back=90)
                    except Exception as e:
                        st.error(f"Błąd komunikacji z GEE: {e}")
                        st.session_state["water_dates"] = []

            w_dates = st.session_state.get("water_dates", [])

            if w_dates:
                selected_water_date = st.selectbox("Wybierz datę bezchmurnego przelotu Sentinel-2:", w_dates)

                if st.button("Generuj mapę zakwitów"):
                    with st.spinner(f"Przeliczanie indeksu NDCI dla daty {selected_water_date}..."):
                        try:
                            tile_url, min_val, max_val = get_water_quality_layer(selected_water_date)

                            if tile_url:
                                m_water = folium.Map(location=[53.7, 14.4], zoom_start=10)

                                folium.TileLayer(
                                    tiles=tile_url,
                                    attr="Google Earth Engine - Sentinel-2 NDCI",
                                    name="Chlorofil-a (NDCI)",
                                    overlay=True,
                                    control=True,
                                    opacity=0.9
                                ).add_to(m_water)

                                colormap = cm.LinearColormap(
                                    colors=['darkblue', 'blue', 'cyan', 'green', 'yellow', 'red'],
                                    vmin=min_val,
                                    vmax=max_val
                                )
                                colormap.caption = "Indeks NDCI (Im cieplejszy kolor, tym większy zakwit/chlorofil)"
                                colormap.add_to(m_water)
                                folium.LayerControl().add_to(m_water)

                                st.success(
                                    "Mapa chlorofilu została wygenerowana! (Ciemnoniebieski = woda czysta, Żółty/Czerwony = zakwity/dużo materii organicznej).")
                                st_folium(m_water, width=1100, height=600, returned_objects=[])
                        except Exception as e:
                            st.error(f"Wystąpił błąd podczas analizy obrazu wodnego: {e}")
            else:
                st.warning("Nie znaleziono bezchmurnych zdjęć dla tego obszaru w ciągu ostatnich 90 dni.")

        # ---------------- MODUŁ 4: DANE WEKTOROWE (OSM) ----------------
        elif modul == "Dane wektorowe (OSM)":
            st.header("🗺️ Baza danych wektorowych - OpenStreetMap (Overpass API)")
            st.markdown(
                "Wybierz obszar Natura 2000, który posłuży jako centrum wyszukiwania, a następnie określ, jakich obiektów szukasz w jego pobliżu.")

            typ_osm = st.radio("Z jakiej bazy wybieramy obszar referencyjny?", ("PLB (Ptaki)", "PLH (Siedliska)"))
            active_data_osm = data_plb if "PLB" in typ_osm else data_plh

            names_osm = [
                f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") or "Bez nazwy"
                for f in active_data_osm["features"]
            ]
            wybrany_osm = st.selectbox("Wybierz obszar Natura 2000 jako centrum poszukiwań:",
                                       sorted(list(set(names_osm))))

            feat_osm = next(
                f for f in active_data_osm["features"]
                if (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany_osm
            )

            # Pobieramy środek wielokąta
            geom_osm = shape(feat_osm["geometry"])
            center_lat = geom_osm.centroid.y
            center_lon = geom_osm.centroid.x

            col1, col2 = st.columns(2)
            with col1:
                promien = st.slider("Promień poszukiwań wokół obszaru (w metrach):", min_value=1000, max_value=20000,
                                    value=5000, step=1000)
            with col2:
                kategoria_osm = st.selectbox(
                    "Czego szukamy?",
                    ("Pomniki przyrody", "Rezerwaty przyrody", "Użytki ekologiczne",
                     "Przejścia dla zwierząt (ekodukty)")
                )

            if st.button("Szukaj w bazie OSM"):
                with st.spinner(f"Wysyłam zapytanie do serwerów Overpass API (Promień: {promien}m)..."):
                    try:
                        osm_results = get_osm_data(center_lat, center_lon, promien, kategoria_osm)
                        elements = osm_results.get("elements", [])

                        m_osm = folium.Map(location=[center_lat, center_lon], zoom_start=11)

                        # Wizualizacja centralnego obszaru referencyjnego
                        folium.GeoJson(
                            feat_osm,
                            style_function=lambda x: {'color': 'gray', 'fillOpacity': 0.1, 'weight': 2}
                        ).add_to(m_osm)

                        # Rysowanie niebieskiego okręgu symbolizującego strefę buforową
                        folium.Circle(
                            location=[center_lat, center_lon],
                            radius=promien,
                            color='blue',
                            fill=True,
                            fill_opacity=0.05
                        ).add_to(m_osm)

                        # Rysowanie pobranych wyników z bazy na mapie
                        if elements:
                            for el in elements:
                                name = el.get("tags", {}).get("name", "Brak nazwy w bazie")

                                if el["type"] == "node":
                                    lat, lon = el["lat"], el["lon"]
                                    folium.Marker([lat, lon], tooltip=name,
                                                  icon=folium.Icon(color="green", icon="leaf")).add_to(m_osm)

                                elif el["type"] in ["way", "relation"] and "geometry" in el:
                                    coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
                                    folium.Polygon(locations=coords, color="green", fill=True, tooltip=name).add_to(
                                        m_osm)

                            st.success(f"Sukces! Znaleziono obiektów w tym promieniu: {len(elements)}")
                        else:
                            st.warning("Nie znaleziono żadnych obiektów tej kategorii w podanym promieniu.")

                        st_folium(m_osm, width=1100, height=600, returned_objects=[])

                        # Przycisk do eksportu wyciągniętych danych
                        if elements:
                            json_string = json.dumps(osm_results, indent=2, ensure_ascii=False)
                            st.download_button(
                                label="📥 Pobierz znalezione wektory jako surowy JSON",
                                data=json_string.encode('utf-8'),
                                file_name=f"osm_wyniki_{kategoria_osm.replace(' ', '_')}.json",
                                mime="application/json"
                            )

                    except Exception as e:
                        st.error(f"Wystąpił błąd podczas pobierania danych przestrzennych: {e}")
    else:
        st.error("Upewnij się, że pliki PLB.geojson i PLH.geojson znajdują się w folderze głównym projektu!")