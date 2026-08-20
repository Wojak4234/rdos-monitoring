# app.py

import streamlit as st
import folium
import pandas as pd
import branca.colormap as cm
import pyproj
from streamlit_folium import st_folium
from shapely.ops import transform
from shapely.geometry import shape, Point, LineString, mapping
import json

from gee_auth import init_gee
from data_loader import load_data
from metadata_utils import get_parameter_info
from osm_fetcher import get_osm_data_bbox
from gios_fetcher import get_gios_stations, get_gios_aqi, get_historical_air_quality
from gee_processor import (
    calculate_index_time_series, get_atmospheric_layer, get_available_dates,
    get_s2_water_dates, get_water_quality_layer
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
                "Pomiary naziemne (GIOŚ)",
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
                            else:
                                st.error("Nie udało się pobrać warstwy.")
                        except Exception as e:
                            st.error(f"Wystąpił błąd silnika Earth Engine: {e}")
            else:
                st.warning(
                    "Niestety nie znaleziono żadnych zdjęć satelitarnych dla tego parametru w ciągu ostatnich 90 dni.")

        # ---------------- MODUŁ 3: STACJE GIOŚ ----------------
        elif modul == "Pomiary naziemne (GIOŚ)":
            st.header("📍 Pomiary naziemne jakości powietrza (API GIOŚ / Copernicus)")
            if "gios_stations" not in st.session_state:
                st.session_state["gios_stations"] = []

            if st.button("Pobierz / Odśwież dane na mapie"):
                with st.spinner("Odpytuję serwery pomiarowe..."):
                    try:
                        stations = get_gios_stations()
                        if stations:
                            for s in stations:
                                aqi, date = get_gios_aqi(s['id'], float(s['gegrLat']), float(s['gegrLon']))
                                s['aqi_level'] = aqi
                                s['calc_date'] = date
                            st.session_state["gios_stations"] = stations
                            st.success(f"Pobrano pomyślnie wskaźniki ogólne dla {len(stations)} lokalizacji.")
                    except Exception as e:
                        st.error(str(e))

            stations_data = st.session_state.get("gios_stations", [])
            if stations_data:
                m_gios = folium.Map(location=[53.6, 15.6], zoom_start=8)
                for s in stations_data:
                    lat = float(s['gegrLat'])
                    lon = float(s['gegrLon'])
                    name = s['stationName']
                    aqi_level = s['aqi_level']
                    calc_date = s['calc_date']

                    color = "gray"
                    if "Bardzo dobry" in aqi_level:
                        color = "darkgreen"
                    elif "Dobry" in aqi_level:
                        color = "green"
                    elif "Umiarkowany" in aqi_level:
                        color = "orange"
                    elif "Dostateczny" in aqi_level or "Zły" in aqi_level:
                        color = "lightred"
                    elif "Bardzo zły" in aqi_level:
                        color = "red"

                    popup_html = f"<b>{name}</b><br>Stan: <b>{aqi_level}</b><br>Czas: {calc_date}"
                    folium.Marker(
                        [lat, lon],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=name,
                        icon=folium.Icon(color=color, icon="info-sign")
                    ).add_to(m_gios)

                st_folium(m_gios, width=1100, height=500, returned_objects=[])

                st.markdown("---")
                st.subheader("📊 Szczegółowe dane zanieczyszczeń i historia (Wykres / Tabela)")
                station_dict = {s['stationName']: s for s in stations_data}
                selected_station = st.selectbox("Wybierz stację z mapy:", list(station_dict.keys()))

                if st.button("Wygeneruj raport szczegółowy (ostatnie 72h)"):
                    with st.spinner("Pobieram pełne dane historyczne..."):
                        sel_s = station_dict[selected_station]
                        df_hist = get_historical_air_quality(float(sel_s['gegrLat']), float(sel_s['gegrLon']),
                                                             past_days=3)

                        if df_hist is not None and not df_hist.empty:
                            st.markdown(f"### Poziom zanieczyszczeń dla stacji: **{selected_station}**")

                            # --- SEKCJA CHECKBOXÓW (MULTICHOICE) ---
                            dostepne_kolumny = df_hist.columns.tolist()
                            wybrane_parametry = st.multiselect(
                                "Zaznacz parametry do wyświetlenia na wykresie i w tabeli:",
                                options=dostepne_kolumny,
                                default=[col for col in ["PM10 (µg/m³)", "PM2.5 (µg/m³)", "NO2 (µg/m³)"] if
                                         col in dostepne_kolumny]
                            )

                            if wybrane_parametry:
                                df_filtered = df_hist[wybrane_parametry]
                                st.line_chart(df_filtered)

                                st.markdown("#### Tabela wyników (Najnowsze na górze)")
                                display_df = df_filtered.tail(24).iloc[::-1]
                                display_df.index = display_df.index.strftime('%Y-%m-%d %H:%M')
                                st.dataframe(display_df, use_container_width=True)

                                csv_hist = display_df.to_csv().encode('utf-8')
                                st.download_button(
                                    label="📥 Pobierz zaznaczone wyniki do CSV",
                                    data=csv_hist,
                                    file_name=f"historia_{selected_station.replace(' ', '_')}.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.warning("Zaznacz przynajmniej jeden parametr powyżej, aby wygenerować wykres.")
                        else:
                            st.error("Brak danych historycznych.")

        # ---------------- MODUŁ 4: JAKOŚĆ WÓD ----------------
        elif modul == "Jakość Wód (Chlorofil-a)":
            st.header("💧 Monitoring jakości wód (Odra i Zalew Szczeciński)")
            if "water_dates" not in st.session_state:
                with st.spinner("Pobieram listę dostępnych dat dla Zalewu Szczecińskiego..."):
                    try:
                        st.session_state["water_dates"] = get_s2_water_dates(days_back=90)
                    except Exception as e:
                        st.error(f"Błąd GEE: {e}")
                        st.session_state["water_dates"] = []

            w_dates = st.session_state.get("water_dates", [])
            if w_dates:
                selected_water_date = st.selectbox("Wybierz datę przelotu Sentinel-2:", w_dates)
                if st.button("Generuj mapę zakwitów"):
                    with st.spinner("Przeliczanie indeksu NDCI..."):
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
                                colormap.caption = "Indeks NDCI"
                                colormap.add_to(m_water)
                                folium.LayerControl().add_to(m_water)

                                st.success("Wygenerowano mapę chlorofilu!")
                                st_folium(m_water, width=1100, height=600, returned_objects=[])
                        except Exception as e:
                            st.error(f"Błąd analizy: {e}")
            else:
                st.warning("Brak bezchmurnych zdjęć w wybranym okresie.")

        # ---------------- MODUŁ 5: DANE WEKTOROWE (OSM) ----------------
        elif modul == "Dane wektorowe (OSM)":
            st.header("🗺️ Baza danych wektorowych - OpenStreetMap (Overpass API)")
            typ_osm = st.radio("Z jakiej bazy wybieramy obszar?", ("PLB (Ptaki)", "PLH (Siedliska)"))
            active_data_osm = data_plb if "PLB" in typ_osm else data_plh

            names_osm = [
                f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") or "Bez nazwy"
                for f in active_data_osm["features"]
            ]
            wybrany_osm = st.selectbox("Wybierz obszar Natura 2000:", sorted(list(set(names_osm))))
            feat_osm = next(
                f for f in active_data_osm["features"]
                if (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany_osm
            )

            col1, col2 = st.columns(2)
            with col1:
                promien = st.slider("Rozmiar bufora (m):", min_value=1000, max_value=20000, value=5000, step=1000)
            with col2:
                kategoria_osm = st.selectbox(
                    "Kategoria:",
                    ("Pomniki przyrody", "Rezerwaty przyrody", "Użytki ekologiczne",
                     "Przejścia dla zwierząt (ekodukty)")
                )

            if st.button("Generuj strefę buforową i wyszukaj"):
                with st.spinner("Przetwarzanie geometryczne i zapytanie OSM..."):
                    try:
                        geom_osm = shape(feat_osm["geometry"])
                        project_to_2180 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2180",
                                                                      always_xy=True).transform
                        project_to_4326 = pyproj.Transformer.from_crs("EPSG:2180", "EPSG:4326",
                                                                      always_xy=True).transform

                        geom_2180 = transform(project_to_2180, geom_osm)
                        buffered_2180 = geom_2180.buffer(promien)
                        buffered_4326 = transform(project_to_4326, buffered_2180)

                        min_lon, min_lat, max_lon, max_lat = buffered_4326.bounds
                        osm_results = get_osm_data_bbox(min_lat, min_lon, max_lon, max_lat, kategoria_osm)
                        elements = osm_results.get("elements", [])

                        filtered_elements = []
                        for el in elements:
                            geom_osm_el = None
                            if el["type"] == "node":
                                geom_osm_el = Point(el["lon"], el["lat"])
                            elif el["type"] in ["way", "relation"] and "geometry" in el:
                                coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
                                if len(coords) >= 2:
                                    geom_osm_el = LineString(coords)

                            if geom_osm_el and buffered_4326.intersects(geom_osm_el):
                                filtered_elements.append(el)

                        m_osm = folium.Map(location=[geom_osm.centroid.y, geom_osm.centroid.x], zoom_start=10)
                        folium.GeoJson(feat_osm, style_function=lambda x: {'color': 'black', 'fillOpacity': 0.4,
                                                                           'weight': 2}).add_to(m_osm)
                        folium.GeoJson(mapping(buffered_4326),
                                       style_function=lambda x: {'color': 'blue', 'fillOpacity': 0.1, 'weight': 2,
                                                                 'dashArray': '5, 5'}).add_to(m_osm)

                        if filtered_elements:
                            for el in filtered_elements:
                                name = el.get("tags", {}).get("name", "Brak nazwy")
                                if el["type"] == "node":
                                    folium.Marker([el["lat"], el["lon"]], tooltip=name,
                                                  icon=folium.Icon(color="green", icon="leaf")).add_to(m_osm)
                                elif el["type"] in ["way", "relation"] and "geometry" in el:
                                    coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
                                    folium.Polygon(locations=coords, color="green", fill=True, tooltip=name).add_to(
                                        m_osm)
                            st.success(f"Znaleziono obiektów: {len(filtered_elements)}")
                        else:
                            st.warning("Brak obiektów w strefie buforowej.")

                        st_folium(m_osm, width=1100, height=600, returned_objects=[])

                        if filtered_elements:
                            osm_results["elements"] = filtered_elements
                            json_string = json.dumps(osm_results, indent=2, ensure_ascii=False)
                            st.download_button(
                                label="📥 Pobierz znalezione wektory jako JSON",
                                data=json_string.encode('utf-8'),
                                file_name=f"osm_bufor_{kategoria_osm.replace(' ', '_')}.json",
                                mime="application/json"
                            )
                    except Exception as e:
                        st.error(f"Błąd: {e}")
    else:
        st.error("Upewnij się, że pliki PLB.geojson i PLH.geojson znajdują się w folderze głównym projektu!")