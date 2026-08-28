import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import unicodedata
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
import branca.colormap as cm


def usun_polskie_znaki(tekst):
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=86400)
def pobierz_rzeczywiste_zasolenie():
    stacje_definicje = {
        "Ujście w Świnoujściu": {"coords": [53.9244, 14.2813], "typ": "Wpływ morski"},
        "Wolin": {"coords": [53.8422, 14.6180], "typ": "Cieśnina Dziwna"},
        "Na północ od Nowego Warpna": {"coords": [53.7578, 14.2979], "typ": "Centralna część Zalewu"},
        "Strefa ujściowa Trzebież": {"coords": [53.7498, 14.5143], "typ": "Strefa przejściowa"},
        "Północne Police (Wielki Krawnik)": {"coords": [53.5831, 14.2985], "typ": "Roztoka Odrzańska"}
    }

    wyniki = {}
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

        for nazwa, info in stacje_definicje.items():
            lat = info["coords"][0]
            lon = info["coords"][1]
            wartosc_so = ostatni_czas['so'].sel(latitude=lat, longitude=lon, method='nearest').isel(depth=0).values
            wyniki[nazwa] = {
                "coords": info["coords"],
                "typ": info["typ"],
                "psu": round(float(wartosc_so), 2)
            }

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

        return wyniki, siatka_gradientu, str(ostatni_czas.time.values)[:10], status_maski, zalew_gdf, df_do_mapy
    except Exception as e:
        return None, None, None, "blad", None, None


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

    with st.spinner("Przetwarzanie zapytań NetCDF i generowanie modelu..."):
        dane_rzeczywiste, siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle = pobierz_rzeczywiste_zasolenie()

    if not dane_rzeczywiste:
        st.warning("Upewnij się, że st.secrets zawiera poprawne poświadczenia OPeNDAP.")
        return

    # --- WYLICZENIE STATYSTYK DO LEGENDY (MIN, MAX, ŚREDNIA) ---
    vals_array = np.array([p["psu"] for p in siatka_gradientu])
    val_min = float(vals_array.min())
    val_max = float(vals_array.max())
    val_mean = float(vals_array.mean())

    st.success(f"✅ Poligon wczytany. Zaktualizowano na dzień: {data_modelu}")

    # Karty KPI na górze (Legenda tekstowa)
    c1, c2, c3 = st.columns(3)
    c1.metric("Minimalne zasolenie", f"{val_min:.2f} PSU")
    c2.metric("Średnie zasolenie obszaru", f"{val_mean:.2f} PSU")
    c3.metric("Maksymalne zasolenie", f"{val_max:.2f} PSU")

    st.subheader("🗺️ Analityczna mapa gradientowa (Interpolacja Cubic)")
    m_zas = folium.Map(location=[53.75, 14.45], zoom_start=10, tiles="OpenStreetMap")

    # Dodanie klasycznej, pływającej legendy barw na mapę
    colormap = cm.LinearColormap(
        colors=['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f', '#ffff00', '#ff7f00', '#ff0000', '#7f0000'],
        vmin=val_min, vmax=val_max
    )
    colormap.caption = 'Zasolenie przestrzenne [PSU]'
    m_zas.add_child(colormap)

    if siatka_gradientu:
        lats = np.array([p["lat"] for p in siatka_gradientu])
        lons = np.array([p["lon"] for p in siatka_gradientu])

        # Pobranie granic poligonu (żeby siatka pokryła go w 100%)
        if status_maski == "zaladowana":
            minx, miny, maxx, maxy = zalew_gdf.total_bounds
        else:
            minx, miny, maxx, maxy = lons.min(), lats.min(), lons.max(), lats.max()

        grid_lon, grid_lat = np.meshgrid(
            np.linspace(minx - 0.02, maxx + 0.02, 500),
            np.linspace(miny - 0.02, maxy + 0.02, 500)
        )

        # Interpolacja: cubic daje gładkość w środku, nearest zapobiega dziurom (NaN) na brzegach
        grid_vals_smooth = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='cubic')
        grid_vals_near = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='nearest')
        grid_vals = np.where(np.isnan(grid_vals_smooth), grid_vals_near, grid_vals_smooth)

        # MASKOWANIE - przycięcie obrazka IDEALNIE do obrysu poligonu
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

        # 'jet' odpowiada palecie barw z legendy
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

        # --- DODANIE INTERAKTYWNOŚCI (HOVER Z WARTOŚCIAMI) ---
        # Dodajemy oryginalne punkty siatki jako absolutnie przezroczyste kółka,
        # które reagują na najechanie myszką i wyświetlają dokładną wartość
        if df_piksle is not None:
            for idx, row in df_piksle.iterrows():
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=12,
                    color='transparent',
                    fill=True,
                    fill_color='transparent',
                    fill_opacity=0,
                    tooltip=f"Estymowane zasolenie:<br><b>{row['so']:.2f} PSU</b>"
                ).add_to(m_zas)

    # Obrysowanie konturów Zalewu za pomocą Twojego GeoJSON
    if status_maski == "zaladowana":
        folium.GeoJson(
            "zalew_maska.geojson",
            name="Linia brzegowa",
            style_function=lambda x: {'color': '#000000', 'weight': 1.5, 'fillOpacity': 0}
        ).add_to(m_zas)

    # Markery stacji punktowych
    for nazwa, info in dane_rzeczywiste.items():
        folium.CircleMarker(
            location=info["coords"], radius=8,
            popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU",
            tooltip=f"Stacja: {nazwa}",
            color="#ffffff", weight=2, fill=True, fill_color="#333333", fill_opacity=1.0
        ).add_to(m_zas)

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
    # 3. SEKCJA WYNIKÓW I EKSPORTU CSV
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Raport ze stacji referencyjnych (Eksport Excel)")

    df_wyniki = pd.DataFrame.from_dict(dane_rzeczywiste, orient='index')
    df_wyniki.index.name = "Stacja"
    df_wyniki.reset_index(inplace=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(df_wyniki[['Stacja', 'typ', 'psu']], use_container_width=True)

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        df_eksport = df_wyniki.copy()
        df_eksport.columns = [usun_polskie_znaki(col) for col in df_eksport.columns]
        df_eksport['Stacja'] = df_eksport['Stacja'].apply(usun_polskie_znaki)
        csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')

        st.download_button(
            label="📥 Pobierz wyniki punktowe (CSV)",
            data=csv_data,
            file_name=f"zasolenie_stacje_{data_modelu}.csv",
            mime="text/csv"
        )