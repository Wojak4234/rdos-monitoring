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


def usun_polskie_znaki(tekst):
    """Usuwa polskie znaki z nagłówków i wartości do poprawnego eksportu CSV"""
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=86400)
def pobierz_rzeczywiste_zasolenie():
    """Pobiera i maskuje zasolenie z modelu CMEMS"""
    stacje_definicje = {
        "Ujście w Świnoujściu": {"coords": [53.9244, 14.2813], "typ": "Wpływ morski"},
        "Wolin": {"coords": [53.8422, 14.6180], "typ": "Cieśnina Dziwna"},
        "Na północ od Nowego Warpna": {"coords": [53.7578, 14.2979], "typ": "Centralna część Zalewu"},
        "Strefa ujściowa Trzebież": {"coords": [53.7498, 14.5143], "typ": "Strefa przejściowa"},
        "Północne Police (Wielki Krawnik)": {"coords": [53.5831, 14.2985], "typ": "Roztoka Odrzańska"}
    }

    wyniki = {}
    siatka_gradientu = []

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

        # 1. POBIERANIE DANYCH PUNKTOWYCH
        for nazwa, info in stacje_definicje.items():
            lat = info["coords"][0]
            lon = info["coords"][1]
            wartosc_so = ostatni_czas['so'].sel(latitude=lat, longitude=lon, method='nearest').isel(depth=0).values

            wyniki[nazwa] = {
                "coords": info["coords"],
                "typ": info["typ"],
                "psu": round(float(wartosc_so), 2)
            }

        # 2. POBIERANIE I MASKOWANIE SIATKI RASTROWEJ
        # Zgrubny BBOX na cały obszar estuarium
        bbox_ds = ostatni_czas['so'].sel(
            latitude=slice(53.40, 54.00),
            longitude=slice(14.15, 14.80)
        ).isel(depth=0)

        df_grid = bbox_ds.to_dataframe().reset_index()
        df_grid = df_grid.dropna(subset=['so'])

        # Maskowanie za pomocą pliku GeoJSON
        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            zalew_gdf = gpd.read_file(maska_path)
            # Przygotowanie geometrii punktowej ze środków pikseli modelu
            geometria = [Point(xy) for xy in zip(df_grid['longitude'], df_grid['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df_grid, geometry=geometria, crs="EPSG:4326")

            # Przecięcie przestrzenne (zostawiamy tylko punkty wpadające w poligon Zalewu)
            clipped_grid = gpd.sjoin(grid_gdf, zalew_gdf, predicate="within")
            df_do_mapy = clipped_grid
        else:
            # Fallback - jeśli brak pliku GeoJSON, pokaże cały BBOX
            df_do_mapy = df_grid

        # Przygotowanie danych do wyrenderowania gradientu
        for index, row in df_do_mapy.iterrows():
            siatka_gradientu.append({
                "lat": row['latitude'],
                "lon": row['longitude'],
                "psu": row['so']
            })

        return wyniki, siatka_gradientu, str(ostatni_czas.time.values)[:10]

    except Exception as e:
        st.error(f"⚠️ Błąd połączenia z API lub przetwarzania danych: {e}")
        return None, None, None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia (Dane Rzeczywiste CMEMS)")
    st.markdown("""
    Autonomiczny moduł analityczny prezentujący przestrzenny rozkład zasolenia [PSU] na podstawie 
    otwartych danych numerycznych (Copernicus Marine Service). Dane maskowane do obszaru Zalewu Szczecińskiego.
    """)

    with st.spinner("Pobieranie macierzy NetCDF i maskowanie przestrzenne..."):
        dane_rzeczywiste, siatka_gradientu, data_modelu = pobierz_rzeczywiste_zasolenie()

    if not dane_rzeczywiste:
        st.warning("Skonfiguruj poprawnie dane logowania w st.secrets i upewnij się, że API odpowiada.")
        return

    st.success(f"✅ Przeprowadzono analizę przestrzenną modelu z dnia: {data_modelu}")

    # ---------------------------------------------------------
    # 1. SEKCJA MAPY INTERAKTYWNEJ
    # ---------------------------------------------------------
    st.subheader("🗺️ Ciągła mapa zasolenia i odczyty punktowe")
    m_zas = folium.Map(location=[53.75, 14.45], zoom_start=10, tiles="CartoDB positron")

    def dobierz_kolor(psu):
        if psu < 1.0:
            return "#2b83ba"  # Słodka (niebieski)
        elif psu < 2.5:
            return "#abdda4"  # Przejściowa (zielonkawy)
        elif psu < 4.5:
            return "#fdae61"  # Słonawa (pomarańczowy)
        else:
            return "#d7191c"  # Morska (czerwony)

    # Przybliżona rozdzielczość piksela modelu CMEMS (ok. 1 mili morskiej w stopniach)
    rozdzielczosc = 0.008

    # Renderowanie siatki wyciętej maską GeoJSON
    for piksel in siatka_gradientu:
        lat = piksel["lat"]
        lon = piksel["lon"]
        psu = piksel["psu"]
        kolor = dobierz_kolor(psu)

        folium.Rectangle(
            bounds=[[lat - rozdzielczosc, lon - rozdzielczosc], [lat + rozdzielczosc, lon + rozdzielczosc]],
            color=kolor,
            weight=0,
            fill=True,
            fill_color=kolor,
            fill_opacity=0.45
        ).add_to(m_zas)

    # Renderowanie precyzyjnych markerów stacji
    for nazwa, info in dane_rzeczywiste.items():
        kolor = dobierz_kolor(info["psu"])
        folium.CircleMarker(
            location=info["coords"], radius=10,
            popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU<br>Typ: {info['typ']}",
            tooltip=f"{nazwa}: {info['psu']} PSU",
            color="#ffffff", weight=2, fill=True, fill_color=kolor, fill_opacity=1.0
        ).add_to(m_zas)

    st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 2. SEKCJA WYNIKÓW I EKSPORTU CSV (Excel)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Wyniki pomiarów na stacjach referencyjnych (PSU)")

    df_wyniki = pd.DataFrame.from_dict(dane_rzeczywiste, orient='index')
    df_wyniki.index.name = "Stacja"
    df_wyniki.reset_index(inplace=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(df_wyniki[['Stacja', 'typ', 'psu']], use_container_width=True)

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)

        # Oczyszczanie danych do pliku eksportowego
        df_eksport = df_wyniki.copy()
        df_eksport.columns = [usun_polskie_znaki(col) for col in df_eksport.columns]
        df_eksport['Stacja'] = df_eksport['Stacja'].apply(usun_polskie_znaki)

        # Generowanie czystego CSV pod polskiego Excela
        csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')

        st.download_button(
            label="📥 Pobierz stacje bazowe do Excela (CSV)",
            data=csv_data,
            file_name=f"zasolenie_estuarium_{data_modelu}.csv",
            mime="text/csv"
        )