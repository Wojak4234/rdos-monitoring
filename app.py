import streamlit as st
import folium
import pandas as pd
import json
import branca.colormap as cm
import pyproj
from streamlit_folium import st_folium
from shapely.ops import transform
from shapely.geometry import shape, Point, LineString, mapping

from gee_auth import init_gee
from data_loader import load_data
from utils import get_parameter_info
from data_fetchers import get_osm_data_bbox, get_gios_stations, get_gios_aqi, get_historical_air_quality
from gee_ops import (
    calculate_index_time_series, get_atmospheric_layer, get_available_dates,
    get_s2_water_dates, get_water_quality_layer
)

st.set_page_config(layout="wide")
st.title("🌱 RDOŚ Monitoring - Ekosystemy i Atmosfera")

if init_gee():
    data_plb = load_data("PLB.geojson")
    data_plh = load_data("PLH.geojson")

    if data_plb and data_plh:
        modul = st.sidebar.radio(
            "Wybierz moduł analizy:",
            ("Obszary Natura 2000 (Wskaźniki)", "Zanieczyszczenie powietrza (S5P)",
             "Pomiary naziemne (GIOŚ)", "Jakość Wód (Chlorofil-a)", "Dane wektorowe (OSM)")
        )

        # --- MODUŁ 1: NATURA 2000 ---
        if modul == "Obszary Natura 2000 (Wskaźniki)":
            typ = st.sidebar.radio("Wybierz kategorię:", ("PLB (Ptaki)", "PLH (Siedliska)"))
            active_data = data_plb if "PLB" in typ else data_plh
            names = [f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") or "Bez nazwy" for f in
                     active_data["features"]]
            wybrany = st.sidebar.selectbox("Wybierz obszar:", sorted(list(set(names))))
            feat = next(f for f in active_data["features"] if
                        (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany)
            geom = shape(feat["geometry"])

            m = folium.Map(location=[geom.centroid.y, geom.centroid.x], zoom_start=11)
            folium.GeoJson(feat, style_function=lambda x: {'color': 'blue' if "PLB" in typ else 'green',
                                                           'fillOpacity': 0.3}).add_to(m)

            idx = st.sidebar.selectbox("Wskaźnik:",
                                       ("NDVI (Wegetacja)", "NDWI (Woda / Mokradła)", "NDMI (Wilgotność roślin)"))
            if st.button("Generuj wykres"):
                df = calculate_index_time_series(feat, idx, pd.to_datetime("2025-01-01"), pd.to_datetime("2026-08-19"))
                if df is not None: st.line_chart(df)
            st_folium(m, width=1100, height=500)

        # --- MODUŁ 2: ZANIECZYSZCZENIE (S5P) ---
        elif modul == "Zanieczyszczenie powietrza (S5P)":
            param = st.selectbox("Parametr:", ("NO2 (Dwutlenek azotu)", "SO2 (Dwutlenek siarki)", "CO (Tlenek węgla)",
                                               "Aerozole (Smog / Pyły)"))
            dates = get_available_dates(param)
            if dates:
                date = st.selectbox("Data:", dates)
                if st.button("Generuj mapę"):
                    url, min_v, max_v = get_atmospheric_layer(date, param)
                    m = folium.Map(location=[53.6, 15.6], zoom_start=8)
                    folium.TileLayer(tiles=url, attr="GEE").add_to(m)
                    cm.LinearColormap(['yellow', 'orange', 'red', 'purple'], vmin=min_v, vmax=max_v).add_to(m)
                    st_folium(m, width=1100, height=600)
                    with st.expander("ℹ️ Informacje"): st.markdown(f"**Opis:** {get_parameter_info(param).get('opis')}")

        # --- MODUŁ 3: GIOŚ ---
        elif modul == "Pomiary naziemne (GIOŚ)":
            if st.button("Pobierz dane"):
                stations = get_gios_stations()
                m = folium.Map(location=[53.6, 15.6], zoom_start=8)
                for s in stations:
                    aqi, date = get_gios_aqi(s['id'], float(s['gegrLat']), float(s['gegrLon']))
                    folium.Marker([float(s['gegrLat']), float(s['gegrLon'])],
                                  popup=f"{s['stationName']}: {aqi}").add_to(m)
                st_folium(m, width=1100, height=500)

                sel = st.selectbox("Stacja:", [s['stationName'] for s in stations])
                if st.button("Historia (ostatnie 72h)"):
                    s = next(st for st in stations if st['stationName'] == sel)
                    df = get_historical_air_quality(float(s['gegrLat']), float(s['gegrLon']))
                    st.line_chart(df)
                    st.dataframe(df)

        # --- MODUŁ 4: WODA ---
        elif modul == "Jakość Wód (Chlorofil-a)":
            dates = get_s2_water_dates()
            sel_date = st.selectbox("Data:", dates)
            if st.button("Generuj mapę"):
                url, min_v, max_v = get_water_quality_layer(sel_date)
                m = folium.Map(location=[53.7, 14.4], zoom_start=10)
                folium.TileLayer(tiles=url, attr="GEE").add_to(m)
                st_folium(m, width=1100, height=600)

        # --- MODUŁ 5: OSM ---
        elif modul == "Dane wektorowe (OSM)":
            typ_osm = st.radio("Baza:", ("PLB", "PLH"))
            ds = data_plb if typ_osm == "PLB" else data_plh
            names = [f["properties"].get("nazwa") or f["properties"].get("SITE_NAME") for f in ds["features"]]
            wybrany = st.selectbox("Obszar:", sorted(list(set(names))))
            feat = next(f for f in ds["features"] if
                        (f["properties"].get("nazwa") or f["properties"].get("SITE_NAME")) == wybrany)
            promien = st.slider("Bufor (m):", 1000, 20000, 5000)
            kat = st.selectbox("Kategoria:", ("Pomniki przyrody", "Rezerwaty przyrody", "Użytki ekologiczne",
                                              "Przejścia dla zwierząt (ekodukty)"))
            if st.button("Szukaj"):
                geom = shape(feat["geometry"])
                proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True).transform
                unproj = pyproj.Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
                buffered = transform(unproj, transform(proj, geom).buffer(promien))
                min_lon, min_lat, max_lon, max_lat = buffered.bounds
                res = get_osm_data_bbox(min_lat, min_lon, max_lat, max_lon, kat)
                m = folium.Map(location=[geom.centroid.y, geom.centroid.x], zoom_start=11)
                for el in res.get("elements", []):
                    if el["type"] == "node": folium.Marker([el["lat"], el["lon"]]).add_to(m)
                st_folium(m, width=1100, height=600)

    else:
        st.error("Brak plików GeoJSON!")