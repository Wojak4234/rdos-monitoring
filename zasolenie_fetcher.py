import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import os
import xarray as xr
import copernicusmarine
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
from matplotlib.path import Path
import io
import base64
from branca.element import Template, MacroElement


@st.cache_data(ttl=86400)
def pobierz_rzeczywiste_zasolenie():
    """Pobiera wyłącznie dane siatkowe dla maski, bez sztucznych stacji."""
    siatka_gradientu = []
    status_maski = "brak"
    zalew_gdf = None
    df_grid_raw = None

    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]

        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_bal_phy_anfc_P1D-m",
            username=user, password=pwd
        )
        ostatni_czas = ds.isel(time=-1)

        # Pobieranie BBOX
        bbox_ds = ostatni_czas['so'].sel(
            latitude=slice(53.40, 54.00),
            longitude=slice(14.15, 14.80)
        ).isel(depth=0)

        df_grid_raw = bbox_ds.to_dataframe().reset_index().dropna(subset=['so'])

        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            status_maski = "zaladowana"
            zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")
            geometria = [Point(xy) for xy in zip(df_grid_raw['longitude'], df_grid_raw['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df_grid_raw, geometry=geometria, crs="EPSG:4326")
            clipped_grid = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")
            df_do_mapy = clipped_grid
        else:
            df_do_mapy = df_grid_raw

        for index, row in df_do_mapy.iterrows():
            siatka_gradientu.append({
                "lat": row['latitude'], "lon": row['longitude'], "psu": row['so']
            })

        return siatka_gradientu, str(ostatni_czas.time.values)[:10], status_maski, zalew_gdf, df_do_mapy
    except Exception as e:
        return None, None, "blad", None, None


@st.cache_data(ttl=86400)
def pobierz_szereg_czasowy_30_dni():
    """Pobiera średnie zasolenie z ostatnich 30 dni dla wyciętego obszaru"""
    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]
        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_bal_phy_anfc_P1D-m",
            username=user, password=pwd
        )

        ostatnie_30 = ds.isel(time=slice(-30, None))
        bbox_ds = ostatnie_30['so'].sel(latitude=slice(53.40, 54.00), longitude=slice(14.15, 14.80)).isel(depth=0)
        df = bbox_ds.to_dataframe().reset_index().dropna(subset=['so'])

        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")
            geom = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            clipped = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")
            df = clipped

        szereg = df.groupby('time')['so'].mean().reset_index()
        szereg.rename(columns={'time': 'Data', 'so': 'Średnie Zasolenie (PSU)'}, inplace=True)
        szereg['Data'] = szereg['Data'].dt.date
        return szereg
    except Exception:
        return None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia (Dane Rzeczywiste CMEMS)")

    with st.spinner("Przetwarzanie zapytań przestrzennych NetCDF..."):
        siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle = pobierz_rzeczywiste_zasolenie()

    if not siatka_gradientu:
        st.warning("Upewnij się, że st.secrets zawiera poprawne poświadczenia OPeNDAP.")
        return

    # --- WYLICZENIE STATYSTYK DLA OBSZARU Z DUŻĄ DOKŁADNOŚCIĄ ---
    vals_array = np.array([p["psu"] for p in siatka_gradientu])
    val_min = float(vals_array.min())
    val_max = float(vals_array.max())
    val_mean = float(vals_array.mean())

    st.success(f"✅ Poligon wczytany. Zaktualizowano na dzień: {data_modelu}")

    # Karty KPI o wysokiej rozdzielczości dziesiętnej
    c1, c2, c3 = st.columns(3)
    c1.metric("Minimalne zasolenie", f"{val_min:.5f} PSU")
    c2.metric("Średnie zasolenie", f"{val_mean:.5f} PSU")
    c3.metric("Maksymalne zasolenie", f"{val_max:.5f} PSU")

    st.subheader("🗺️ Analityczna mapa gradientowa (Interpolacja Cubic)")
    m_zas = folium.Map(location=[53.75, 14.45], zoom_start=10, tiles="OpenStreetMap")

    if siatka_gradientu:
        lats = np.array([p["lat"] for p in siatka_gradientu])
        lons = np.array([p["lon"] for p in siatka_gradientu])

        # Pobranie granic poligonu
        if status_maski == "zaladowana":
            minx, miny, maxx, maxy = zalew_gdf.total_bounds
        else:
            minx, miny, maxx, maxy = lons.min(), lats.min(), lons.max(), lats.max()

        grid_lon, grid_lat = np.meshgrid(
            np.linspace(minx - 0.02, maxx + 0.02, 500),
            np.linspace(miny - 0.02, maxy + 0.02, 500)
        )

        grid_vals_smooth = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='cubic')
        grid_vals_near = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='nearest')
        grid_vals = np.where(np.isnan(grid_vals_smooth), grid_vals_near, grid_vals_smooth)

        # Maskowanie - przycięcie obrazka IDEALNIE do obrysu poligonu
        if status_maski == "zaladowana":
            pts = np.vstack((grid_lon.flatten(), grid_lat.flatten())).T
            mask = np.zeros(pts.shape[0], dtype=bool)
            for geom in zalew_gdf.geometry:
                if geom.type == 'Polygon':
                    mask = mask | Path(np.asarray(geom.exterior.coords)).contains_points(pts)
                elif geom.type == 'MultiPolygon':
                    for poly in geom.geoms:
                        mask = mask | Path(np.asarray(poly.exterior.coords)).contains_points(pts)
            grid_vals.flat[~mask] = np.nan

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        contour = ax.contourf(grid_lon, grid_lat, grid_vals, levels=50, cmap='jet', alpha=0.65)

        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
        img_buf.seek(0)
        img_base64 = base64.b64encode(img_buf.read()).decode('utf-8')
        plt.close(fig)

        img_bounds = [[miny - 0.02, minx - 0.02], [maxy + 0.02, maxx + 0.02]]
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{img_base64}",
            bounds=img_bounds,
            opacity=0.75,
            name="Gradient zasolenia"
        ).add_to(m_zas)

        # --- DODANIE INTERAKTYWNOŚCI (HOVER Z WARTOŚCIAMI 6 CYFR) ---
        if df_piksle is not None:
            for idx, row in df_piksle.iterrows():
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=12,
                    color='transparent',
                    fill=True,
                    fill_color='transparent',
                    fill_opacity=0,
                    tooltip=f"Węzeł modelu:<br><b>{row['so']:.6f} PSU</b>"
                ).add_to(m_zas)

    # Obrysowanie konturów Zalewu
    if status_maski == "zaladowana":
        folium.GeoJson(
            "zalew_maska.geojson",
            name="Linia brzegowa",
            style_function=lambda x: {'color': '#000000', 'weight': 1.5, 'fillOpacity': 0}
        ).add_to(m_zas)

    # --- PIONOWA LEGENDA HTML/CSS ---
    macro_html = f"""
    {{% macro html(this, kwargs) %}}
    <div style="
        position: fixed; 
        bottom: 50px;
        right: 50px;
        width: 130px;
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
        <b>Zasolenie<br>[PSU]</b><br><br>
        <div style="display: flex; flex-direction: row; height: 180px;">
            <div style="
                background: linear-gradient(to top, 
                    #00007f 0%, #0000ff 12.5%, #007fff 25%, #00ffff 37.5%, 
                    #7fff7f 50%, #ffff00 62.5%, #ff7f00 75%, #ff0000 87.5%, #7f0000 100%);
                width: 25px;
                height: 100%;
                border: 1px solid #555;
                ">
            </div>
            <div style="display: flex; flex-direction: column; justify-content: space-between; margin-left: 10px; height: 100%;">
                <span>{val_max:.4f}</span>
                <span>{val_min + (val_max - val_min) * 0.75:.4f}</span>
                <span>{val_min + (val_max - val_min) * 0.5:.4f}</span>
                <span>{val_min + (val_max - val_min) * 0.25:.4f}</span>
                <span>{val_min:.4f}</span>
            </div>
        </div>
    </div>
    {{% endmacro %}}
    """
    macro = MacroElement()
    macro._template = Template(macro_html)
    m_zas.add_child(macro)

    st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 2. SEKCJA ANALIZY CZASOWEJ (OSTATNIE 30 DNI)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Dynamika zasolenia estuarium (Ostatnie 30 dni)")

    with st.spinner("Pobieranie i agregacja danych z ostatniego miesiąca..."):
        szereg_df = pobierz_szereg_czasowy_30_dni()

    if szereg_df is not None:
        st.line_chart(szereg_df.set_index('Data'), color="#007fff")
    else:
        st.info("Brak możliwości wygenerowania trendu 30-dniowego.")

    # ---------------------------------------------------------
    # 3. SEKCJA RAPORTU Z WEZŁÓW SIATKI (Zamiast sztucznych punktów)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Raport danych przestrzennych siatki modelu (Eksport Excel)")

    # Przygotowanie pełnych danych z siatki przestrzennej
    df_eksport = df_piksle[['latitude', 'longitude', 'so']].copy()
    df_eksport.rename(columns={
        'latitude': 'Szerokosc Geograficzna',
        'longitude': 'Dlugosc Geograficzna',
        'so': 'Zasolenie (PSU)'
    }, inplace=True)
    df_eksport.reset_index(drop=True, inplace=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(df_eksport, use_container_width=True)

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')


        st.download_button(
            label="📥 Pobierz węzły siatki (CSV)",
            data=csv_data,
            file_name=f"zasolenie_siatka_{data_modelu}.csv",
            mime="text/csv"
        )