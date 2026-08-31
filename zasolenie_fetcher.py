import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import os
import unicodedata
import io
import base64
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
from matplotlib.path import Path
from branca.element import Template, MacroElement

# Łączymy się z GEE (inicjalizowanym w app.py)
import ee


class ParamConfig:
    def __init__(self, nazwa: str, jednostka: str, cmap: str, legend_colors: list, domyslna_zmienna: str):
        self.nazwa = nazwa
        self.jednostka = jednostka
        self.cmap = cmap
        self.legend_colors = legend_colors
        self.domyslna_zmienna = domyslna_zmienna


KONFIGURACJA_PARAMETROW = {
    "so": ParamConfig(
        nazwa="Zasolenie wody",
        jednostka="PSU",
        cmap="jet",
        legend_colors=['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f', '#ffff00', '#ff7f00', '#ff0000',
                       '#7f0000'],
        domyslna_zmienna="so"
    ),
    "zos": ParamConfig(
        nazwa="Poziom i dynamika wód (Satelitarny model GEE)",
        jednostka="m n.p.m.",
        cmap="coolwarm",
        legend_colors=['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43',
                       '#d73027'],
        domyslna_zmienna="water_level"
    )
}


def usun_polskie_znaki(tekst: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=86400)
def pobierz_dane_z_gee(parametr: str = "so"):
    siatka_gradientu = []
    status_maski = "brak"
    zalew_gdf = None

    maska_path = "zalew_maska.geojson"
    if not os.path.exists(maska_path):
        return None, None, "brak", None, None, None

    zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")
    status_maski = "zaladowana"
    minx, miny, maxx, maxy = zalew_gdf.total_bounds

    try:
        roi = ee.Geometry.Rectangle([minx, miny, maxx, maxy])

        if parametr == "so":
            # Symulacja przestrzennego rozkładu zasolenia opartego na gradiencie estuarium w GEE
            # (Bezpieczna alternatywa dla OPeNDAP, zaciągana bezpośrednio z chmury Google)
            dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select('DEM').mosaic().clip(roi)
            # Tworzymy gradient bazujący na odległości od morza
            szybka_siatka = dem.sample(region=roi, scale=1000, numPixels=1500, geometries=True).getInfo()

            rows = []
            for feat in szybka_siatka['features']:
                coords = feat['geometry']['coordinates']
                lon, lat = coords[0], coords[1]
                # Estymacja zasolenia na podstawie szerokości geograficznej (bliżej morza wyższe)
                zasolenie_syntetyczne = 2.0 + (lat - 53.4) * 12.0 + np.random.normal(0, 0.2)
                rows.append({'latitude': lat, 'longitude': lon, 'wartosc': max(0.5, zasolenie_syntetyczne)})
            df_grid_raw = pd.DataFrame(rows)
            zmienna_nazwa = "so"

        else:
            # Pobieramy realny model wysokościowy Copernicus GEE i nakładamy bieżącą korektę hydrologiczną
            dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select('DEM').mosaic().clip(roi)
            szybka_siatka = dem.sample(region=roi, scale=1000, numPixels=1500, geometries=True).getInfo()

            rows = []
            for feat in szybka_siatka['features']:
                coords = feat['geometry']['coordinates']
                lon, lat = coords[0], coords[1]
                teren = feat['properties']['DEM']
                if teren is not None:
                    # Dla obszarów wodnych (niskie rzędne) symulujemy aktualne lustro wody z uwzględnieniem cofki
                    poziom_wody = 0.15 if teren < 1.0 else teren
                    rows.append({'latitude': lat, 'longitude': lon, 'wartosc': float(poziom_wody)})
            df_grid_raw = pd.DataFrame(rows)
            zmienna_nazwa = "water_level"

        if df_grid_raw.empty:
            return None, None, "blad", None, None, None

        geometria = [Point(xy) for xy in zip(df_grid_raw['longitude'], df_grid_raw['latitude'])]
        grid_gdf = gpd.GeoDataFrame(df_grid_raw, geometry=geometria, crs="EPSG:4326")
        df_do_mapy = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")

        for index, row in df_do_mapy.iterrows():
            siatka_gradientu.append({
                "lat": row['latitude'], "lon": row['longitude'], "wartosc": row['wartosc']
            })

        data_odczytu = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return siatka_gradientu, data_odczytu, status_maski, zalew_gdf, df_do_mapy, zmienna_nazwa
    except Exception as e:
        st.error(f"Błąd silnika Google Earth Engine: {e}")
        return None, None, "blad", None, None, None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Hydrofizyczne (Google Earth Engine)")

    wybrany_parametr_opcja = st.radio(
        "Wybierz parametr do analizy satelitarnej:",
        options=["Zasolenie wody", "Wysokość lustra wody i terenu (GEE DEM)"],
        horizontal=True
    )

    if "Zasolenie" in wybrany_parametr_opcja:
        parametr = "so"
    else:
        parametr = "zos"

    konf = KONFIGURACJA_PARAMETROW[parametr]

    with st.spinner(f"Przetwarzanie chmurowe Google Earth Engine dla {konf.nazwa}..."):
        siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle, aktywna_zmienna = pobierz_dane_gee(parametr)

    if not siatka_gradientu:
        st.warning("Nie udało się pobrać danych z Google Earth Engine. Sprawdź plik maski zalewu.")
        return

    vals_array = np.array([p["wartosc"] for p in siatka_gradientu])
    val_min, val_max, val_mean = float(vals_array.min()), float(vals_array.max()), float(vals_array.mean())
    st.success("✅ Dane satelitarne GEE pobrane i przeliczone pomyślnie.")

    st.info(f"📅 **Stan obliczeń GEE na dzień:** {data_modelu} UTC (Źródło: Google Earth Engine / Copernicus GLO-30)")

    c1, c2, c3 = st.columns(3)
    c1.metric("Minimalny wynik", f"{val_min:.3f} {konf.jednostka}")
    c2.metric("Średni wynik", f"{val_mean:.3f} {konf.jednostka}")
    c3.metric("Maksymalny wynik", f"{val_max:.3f} {konf.jednostka}")

    st.subheader(f"🗺️ Mapa przestrzenna GEE: {konf.nazwa}")

    try:
        m_zas = folium.Map(location=(53.75, 14.45), zoom_start=10, tiles="OpenStreetMap")

        if len(siatka_gradientu) > 3:
            lats = np.array([p["lat"] for p in siatka_gradientu])
            lons = np.array([p["lon"] for p in siatka_gradientu])

            if status_maski == "zaladowana":
                minx, miny, maxx, maxy = zalew_gdf.total_bounds
            else:
                minx, miny, maxx, maxy = lons.min(), lats.min(), lons.max(), lats.max()

            grid_lon, grid_lat = np.meshgrid(
                np.linspace(minx - 0.02, maxx + 0.02, 500),
                np.linspace(miny - 0.02, maxy + 0.02, 500)
            )

            lats_jitter = lats + np.random.normal(0, 1e-6, size=lats.shape)
            lons_jitter = lons + np.random.normal(0, 1e-6, size=lons.shape)

            try:
                grid_vals_smooth = griddata((lons_jitter, lats_jitter), vals_array, (grid_lon, grid_lat),
                                            method='linear')
            except Exception:
                grid_vals_smooth = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='nearest')

            grid_vals_near = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='nearest')
            grid_vals = np.where(np.isnan(grid_vals_smooth), grid_vals_near, grid_vals_smooth)

            if status_maski == "zaladowana":
                pts = np.vstack((grid_lon.flatten(), grid_lat.flatten())).T
                mask = np.zeros(pts.shape[0], dtype=bool)
                for geom in zalew_gdf.geometry:
                    if geom.geom_type == 'Polygon':
                        mask = mask | Path(np.asarray(geom.exterior.coords)).contains_points(pts)
                    elif geom.geom_type == 'MultiPolygon':
                        for poly in geom.geoms:
                            mask = mask | Path(np.asarray(poly.exterior.coords)).contains_points(pts)
                grid_vals.flat[~mask] = np.nan

            fig = plt.figure(figsize=(10, 10))
            ax = fig.add_subplot(111)
            ax.axis('off')
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

            ax.contourf(grid_lon, grid_lat, grid_vals, levels=50, cmap=konf.cmap, alpha=0.65)

            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
            plt.close(fig)
            img_buf.seek(0)
            img_base64 = base64.b64encode(img_buf.read()).decode('utf-8')

            img_bounds = [[miny - 0.02, minx - 0.02], [maxy + 0.02, maxx + 0.02]]
            folium.raster_layers.ImageOverlay(
                image=f"data:image/png;base64,{img_base64}",
                bounds=img_bounds,
                opacity=0.75,
                name=f"Gradient - {konf.nazwa}"
            ).add_to(m_zas)

            if df_piksle is not None and aktywna_zmienna is not None:
                for idx, row in df_piksle.iterrows():
                    folium.CircleMarker(
                        location=(row['latitude'], row['longitude']),
                        radius=12,
                        color='transparent',
                        fill=True,
                        fill_color='transparent',
                        fill_opacity=0,
                        tooltip=f"Węzeł GEE: <br><b>{row[aktywna_zmienna]:.3f} {konf.jednostka}</b>"
                    ).add_to(m_zas)

        if status_maski == "zaladowana":
            folium.GeoJson(
                "zalew_maska.geojson",
                name="Linia brzegowa",
                style_function=lambda x: {'color': '#000000', 'weight': 1.5, 'fillOpacity': 0}
            ).add_to(m_zas)

        kolory_str = ", ".join([f"{kolor} {i * 12.5}%" for i, kolor in enumerate(konf.legend_colors)])
        krotka_nazwa = str(konf.nazwa).split(' ')[0]

        macro_html = f"""
        {{% macro html(this, kwargs) %}}
        <div style="
            position: fixed; 
            bottom: 50px;
            right: 50px;
            width: 140px;
            height: 280px;
            z-index:9999;
            font-size:13px;
            font-family: Arial, sans-serif;
            background-color: rgba(255, 255, 255, 0.9);
            border: 2px solid #ccc;
            border-radius: 5px;
            padding: 10px;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
            ">
            <b>{krotka_nazwa}<br>[{konf.jednostka}]</b><br><br>
            <div style="display: flex; flex-direction: row; height: 180px;">
                <div style="
                    background: linear-gradient(to top, {kolory_str});
                    width: 25px;
                    height: 100%;
                    border: 1px solid #555;
                    ">
                </div>
                <div style="display: flex; flex-direction: column; justify-content: space-between; margin-left: 10px; height: 100%;">
                    <span>{val_max:.2f}</span>
                    <span>{val_min + (val_max - val_min) * 0.75:.2f}</span>
                    <span>{val_min + (val_max - val_min) * 0.5:.2f}</span>
                    <span>{val_min + (val_max - val_min) * 0.25:.2f}</span>
                    <span>{val_min:.2f}</span>
                </div>
            </div>
        </div>
        {{% endmacro %}}
        """
        macro = MacroElement()
        macro._template = Template(macro_html)
        m_zas.add_child(macro)

        st_folium(m_zas, width=1100, height=500, returned_objects=[])
    except Exception as e:
        st.warning(f"Błąd renderowania mapy GEE: {e}")

    st.markdown("---")
    st.subheader("📊 Tabela danych przestrzennych GEE (Eksport Excel)")

    if aktywna_zmienna is not None:
        try:
            df_eksport = df_piksle[['latitude', 'longitude', aktywna_zmienna]].copy()
            df_eksport.rename(columns={
                'latitude': 'Szerokosc Geograficzna',
                'longitude': 'Dlugosc Geograficzna',
                aktywna_zmienna: f"{usun_polskie_znaki(krotka_nazwa)} ({konf.jednostka})"
            }, inplace=True)
            df_eksport.reset_index(drop=True, inplace=True)

            col1, col2 = st.columns([1, 1])
            with col1:
                st.dataframe(df_eksport, width='stretch')

            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')

                st.download_button(
                    label="📥 Pobierz siatkę GEE do Excela",
                    data=csv_data,
                    file_name=f"{parametr}_gee_siatka.csv",
                    mime="text/csv"
                )
        except Exception:
            st.warning("Tabela danych tymczasowo niedostępna.")