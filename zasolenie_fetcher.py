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
import io
import base64


def usun_polskie_znaki(tekst):
    """Usuwa polskie znaki z nagłówków do poprawnego eksportu CSV"""
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

    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]

        # Otwarcie zbioru danych OPeNDAP
        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_bal_phy_anfc_P1D-m",
            username=user,
            password=pwd
        )

        ostatni_czas = ds.isel(time=-1)

        # 1. POBIERANIE PUNKTOWE (Dla stacji referencyjnych)
        for nazwa, info in stacje_definicje.items():
            lat = info["coords"][0]
            lon = info["coords"][1]
            wartosc_so = ostatni_czas['so'].sel(latitude=lat, longitude=lon, method='nearest').isel(depth=0).values

            wyniki[nazwa] = {
                "coords": info["coords"],
                "typ": info["typ"],
                "psu": round(float(wartosc_so), 2)
            }

        # 2. POBIERANIE SIATKI RASTROWEJ
        bbox_ds = ostatni_czas['so'].sel(
            latitude=slice(53.40, 54.00),
            longitude=slice(14.15, 14.80)
        ).isel(depth=0)

        df_grid = bbox_ds.to_dataframe().reset_index().dropna(subset=['so'])

        # Maskowanie za pomocą pliku GeoJSON
        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            status_maski = "zaladowana"
            zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")

            geometria = [Point(xy) for xy in zip(df_grid['longitude'], df_grid['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df_grid, geometry=geometria, crs="EPSG:4326")

            # Zostawiamy punkty stykające się z estuarium
            clipped_grid = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")
            df_do_mapy = clipped_grid
        else:
            df_do_mapy = df_grid

        for index, row in df_do_mapy.iterrows():
            siatka_gradientu.append({
                "lat": row['latitude'],
                "lon": row['longitude'],
                "psu": row['so']
            })

        return wyniki, siatka_gradientu, str(ostatni_czas.time.values)[:10], status_maski

    except Exception as e:
        st.error(f"⚠️ Błąd połączenia z API lub przetwarzania danych: {e}")
        return None, None, None, "blad"


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia (Dane Rzeczywiste CMEMS)")

    with st.spinner("Pobieranie macierzy NetCDF i maskowanie przestrzenne..."):
        dane_rzeczywiste, siatka_gradientu, data_modelu, status_maski = pobierz_rzeczywiste_zasolenie()

    if not dane_rzeczywiste:
        st.warning("Upewnij się, że st.secrets zawiera poprawne poświadczenia OPeNDAP.")
        return

    st.success(f"✅ Przeprowadzono analizę przestrzenną modelu z dnia: {data_modelu}")

    # ---------------------------------------------------------
    # 1. SEKCJA MAPY INTERAKTYWNEJ
    # ---------------------------------------------------------
    st.subheader("🗺️ Analityczna mapa gradientowa")

    # Zmiana mapy bazowej na darmową, bez znaków wodnych (jak w GEE)
    m_zas = folium.Map(location=[53.75, 14.45], zoom_start=10, tiles="OpenStreetMap")

    # --- SEKCJA GENEROWANIA GŁADKIEGO RASTRA ---
    if siatka_gradientu:
        lats = np.array([p["lat"] for p in siatka_gradientu])
        lons = np.array([p["lon"] for p in siatka_gradientu])
        vals = np.array([p["psu"] for p in siatka_gradientu])

        # Zagęszczenie siatki dla płynnego gradientu
        grid_lon, grid_lat = np.meshgrid(
            np.linspace(lons.min() - 0.01, lons.max() + 0.01, 400),
            np.linspace(lats.min() - 0.01, lats.max() + 0.01, 400)
        )

        # Interpolacja sześcienna (cubic)
        grid_vals = griddata((lons, lats), vals, (grid_lon, grid_lat), method='cubic')

        # Wygenerowanie obrazu za pomocą Matplotlib
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        # Rysowanie mapy cieplnej (cmap='jet' dla efektu od niebieskiego po czerwony)
        contour = ax.contourf(grid_lon, grid_lat, grid_vals, levels=30, cmap='jet', alpha=0.65)

        # Zapis do przezroczystego PNG w pamięci podręcznej
        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
        img_buf.seek(0)
        img_base64 = base64.b64encode(img_buf.read()).decode('utf-8')
        plt.close(fig)

        # Nałożenie obrazu na mapę Folium
        img_bounds = [[lats.min() - 0.01, lons.min() - 0.01], [lats.max() + 0.01, lons.max() + 0.01]]
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{img_base64}",
            bounds=img_bounds,
            opacity=0.7,
            name="Gradient zasolenia"
        ).add_to(m_zas)

    # Obrysowanie konturów Zalewu za pomocą Twojego GeoJSON
    if status_maski == "zaladowana":
        folium.GeoJson(
            "zalew_maska.geojson",
            name="Linia brzegowa",
            style_function=lambda x: {'color': '#333333', 'weight': 1.5, 'fillOpacity': 0}
        ).add_to(m_zas)

    # Markery stacji referencyjnych (na wierzchu)
    def dobierz_kolor(psu):
        if psu < 1.0:
            return "#2b83ba"
        elif psu < 2.5:
            return "#abdda4"
        elif psu < 4.5:
            return "#fdae61"
        else:
            return "#d7191c"

    for nazwa, info in dane_rzeczywiste.items():
        kolor = dobierz_kolor(info["psu"])
        folium.CircleMarker(
            location=info["coords"], radius=9,
            popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU",
            tooltip=f"{nazwa}: {info['psu']} PSU",
            color="#ffffff", weight=2, fill=True, fill_color=kolor, fill_opacity=1.0
        ).add_to(m_zas)

    st_folium(m_zas, width=1100, height=500, returned_objects=[])

    st.markdown(
        "<p style='text-align: center; color: gray; font-size: 12px;'>Wykonano na potrzeby RDOŚ Monitoring | Wykonał: Wojciech Świątek</p>",
        unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 2. SEKCJA WYNIKÓW I EKSPORTU CSV
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Agregacja wyników punktowych (PSU)")

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
            label="📥 Wygeneruj zrzut referencyjny (CSV)",
            data=csv_data,
            file_name=f"zasolenie_estuarium_{data_modelu}.csv",
            mime="text/csv"
        )