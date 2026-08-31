import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import os
import unicodedata
import io
import base64
import copernicusmarine
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
from matplotlib.path import Path
from branca.element import Template, MacroElement


# Klasa konfiguracyjna
class ParamConfig:
    def __init__(self, nazwa: str, jednostka: str, cmap: str, legend_colors: list, dataset_id: str, zmienna: str):
        self.nazwa = nazwa
        self.jednostka = jednostka
        self.cmap = cmap
        self.legend_colors = legend_colors
        self.dataset_id = dataset_id
        self.zmienna = zmienna


KONFIGURACJA_PARAMETROW = {
    "so": ParamConfig(
        nazwa="Zasolenie wody",
        jednostka="PSU",
        cmap="jet",
        legend_colors=['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f', '#ffff00', '#ff7f00', '#ff0000',
                       '#7f0000'],
        dataset_id="cmems_mod_bal_phy_anfc_P1D-m",  # Model 3D Bałtyku (średnia dobowa)
        zmienna="so"
    ),
    "zos": ParamConfig(
        nazwa="Wysokość lustra wody (Bieżące wezbranie)",
        jednostka="m",
        cmap="coolwarm",
        legend_colors=['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43',
                       '#d73027'],
        dataset_id="cmems_mod_bal_phy_anfc_PT1H-i",  # Model 2D Bałtyku (dane live godzinowe, "i" - instantaneous)
        zmienna="slev"
    )
}


def usun_polskie_znaki(tekst: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=3600)
def pobierz_rzeczywiste_dane(parametr: str = "so"):
    siatka_gradientu = []
    status_maski = "brak"
    zalew_gdf = None

    konf = KONFIGURACJA_PARAMETROW[parametr]

    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]

        ds = copernicusmarine.open_dataset(
            dataset_id=konf.dataset_id,
            username=user, password=pwd
        )

        # Pancerne wykrywanie zmiennej w pliku
        dostepne_zmienne = list(ds.data_vars.keys())
        zmienna_docelowa = konf.zmienna
        if zmienna_docelowa not in dostepne_zmienne:
            if "zos" in dostepne_zmienne:
                zmienna_docelowa = "zos"
            elif "slev" in dostepne_zmienne:
                zmienna_docelowa = "slev"
            elif "so" in dostepne_zmienne:
                zmienna_docelowa = "so"
            else:
                raise ValueError(f"Nie znaleziono odpowiedniej zmiennej w zbiorze. Dostępne: {dostepne_zmienne}")

        # Odrzucamy prognozy z przyszłości. Pobieramy stan historyczny/dzisiejszy
        dzisiaj = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
        ostatni_czas = ds.sel(time=dzisiaj, method='nearest')

        bbox_ds = ostatni_czas[zmienna_docelowa].sel(
            latitude=slice(53.40, 54.00),
            longitude=slice(14.15, 14.80)
        )

        # Jeśli to zmienna 3D (Zasolenie), ucinamy wymiar głębokości do zera
        try:
            bbox_ds = bbox_ds.isel(depth=0)
        except Exception:
            pass

        df_grid_raw = bbox_ds.to_dataframe().reset_index().dropna(subset=[zmienna_docelowa])

        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            status_maski = "zaladowana"
            zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")
            geometria = [Point(xy) for xy in zip(df_grid_raw['longitude'], df_grid_raw['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df_grid_raw, geometry=geometria, crs="EPSG:4326")
            df_do_mapy = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")
        else:
            df_do_mapy = df_grid_raw

        for index, row in df_do_mapy.iterrows():
            siatka_gradientu.append({
                "lat": row['latitude'], "lon": row['longitude'], "wartosc": row[zmienna_docelowa]
            })

        data_odczytu = str(ostatni_czas.time.values)[:16].replace("T", " ")
        return siatka_gradientu, data_odczytu, status_maski, zalew_gdf, df_do_mapy, zmienna_docelowa
    except Exception as e:
        st.error(f"Błąd pobierania danych z Copernicusa: {e}")
        return None, None, "blad", None, None, None


@st.cache_data(ttl=86400)
def pobierz_szereg_czasowy_30_dni(parametr: str = "so"):
    konf = KONFIGURACJA_PARAMETROW[parametr]
    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]
        ds = copernicusmarine.open_dataset(
            dataset_id=konf.dataset_id,
            username=user, password=pwd
        )

        dostepne_zmienne = list(ds.data_vars.keys())
        zmienna_docelowa = konf.zmienna
        if zmienna_docelowa not in dostepne_zmienne:
            if "zos" in dostepne_zmienne:
                zmienna_docelowa = "zos"
            elif "slev" in dostepne_zmienne:
                zmienna_docelowa = "slev"
            elif "so" in dostepne_zmienne:
                zmienna_docelowa = "so"

        # Filtrujemy dane do dzisiejszej daty (odcinamy prognozy)
        dzisiaj = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
        trzydziesci_dni_temu = dzisiaj - pd.Timedelta(days=30)

        ostatnie_30 = ds.sel(time=slice(trzydziesci_dni_temu, dzisiaj))

        # Oszczędzamy pamięć - z modelu godzinowego bierzemy próbkę co 24h na potrzeby trendu
        if "PT1H" in konf.dataset_id:
            ostatnie_30 = ostatnie_30.isel(time=slice(None, None, 24))

        bbox_ds = ostatnie_30[zmienna_docelowa].sel(latitude=slice(53.40, 54.00), longitude=slice(14.15, 14.80))

        try:
            bbox_ds = bbox_ds.isel(depth=0)
        except Exception:
            pass

        df = bbox_ds.to_dataframe().reset_index().dropna(subset=[zmienna_docelowa])

        maska_path = "zalew_maska.geojson"
        if os.path.exists(maska_path):
            zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")
            geom = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
            grid_gdf = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            df = gpd.sjoin(grid_gdf, zalew_gdf, predicate="intersects")

        szereg = df.groupby('time')[zmienna_docelowa].mean().reset_index()
        szereg.rename(columns={'time': 'Data', zmienna_docelowa: f"Średnia ({konf.jednostka})"}, inplace=True)
        szereg['Data'] = pd.to_datetime(szereg['Data']).dt.date
        return szereg
    except Exception:
        return None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Hydrofizyczne (Dynamiczne Modele CMEMS)")

    wybrany_parametr_opcja = st.radio(
        "Wybierz bieżący parametr do analizy:",
        options=["Zasolenie wody", "Wysokość lustra wody (Podtopienia/Przejezdność)"],
        horizontal=True
    )

    if "Zasolenie" in wybrany_parametr_opcja:
        parametr = "so"
    else:
        parametr = "zos"

    konf = KONFIGURACJA_PARAMETROW[parametr]

    with st.spinner(f"Odpytuję najnowsze mapy Copernicus ({konf.dataset_id})..."):
        siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle, aktywna_zmienna = pobierz_rzeczywiste_dane(
            parametr)

    if not siatka_gradientu:
        st.warning(
            "Upewnij się, że st.secrets zawiera poprawne poświadczenia OPeNDAP dla Copernicusa i model istnieje.")
        return

    vals_array = np.array([p["wartosc"] for p in siatka_gradientu])
    val_min, val_max, val_mean = float(vals_array.min()), float(vals_array.max()), float(vals_array.mean())
    st.success("✅ Dane pobrane i przeliczone przestrzennie pomyślnie.")

    st.info(f"📅 **Stan faktyczny na:** {data_modelu} UTC")

    # --- KARTY KPI ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Minimalny wynik", f"{val_min:.3f} {konf.jednostka}")
    c2.metric("Średni wynik", f"{val_mean:.3f} {konf.jednostka}")
    c3.metric("Maksymalny wynik", f"{val_max:.3f} {konf.jednostka}")

    # --- MAPA INTERAKTYWNA ---
    st.subheader(f"🗺️ Bieżąca mapa przestrzenna: {konf.nazwa}")
    m_zas = folium.Map(location=(53.75, 14.45), zoom_start=10, tiles="OpenStreetMap")

    if siatka_gradientu:
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

        grid_vals_smooth = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='cubic')
        grid_vals_near = griddata((lons, lats), vals_array, (grid_lon, grid_lat), method='nearest')
        grid_vals = np.where(np.isnan(grid_vals_smooth), grid_vals_near, grid_vals_smooth)

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

        ax.contourf(grid_lon, grid_lat, grid_vals, levels=50, cmap=konf.cmap, alpha=0.65)

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
                    tooltip=f"Odczyt węzła z {data_modelu}: <br><b>{row[aktywna_zmienna]:.3f} {konf.jednostka}</b>"
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

    # --- HISTORIA ---
    st.markdown("---")
    st.subheader(f"📈 Dynamika zmian - {konf.nazwa} (Ostatnie 30 dni wstecz od dzisiaj)")
    with st.spinner("Pobieranie danych historycznych z CMEMS..."):
        szereg_df = pobierz_szereg_czasowy_30_dni(parametr)
    if szereg_df is not None:
        st.line_chart(szereg_df.set_index('Data'), color="#007fff" if parametr == "so" else "#d73027")
    else:
        st.info("Brak możliwości wygenerowania trendu 30-dniowego.")

    # --- EKSPORT SIATKI ---
    st.markdown("---")
    st.subheader("📊 Tabela danych przestrzennych (Eksport Excel)")

    if aktywna_zmienna is not None:
        df_eksport = df_piksle[['latitude', 'longitude', aktywna_zmienna]].copy()
        df_eksport.rename(columns={
            'latitude': 'Szerokosc Geograficzna',
            'longitude': 'Dlugosc Geograficzna',
            aktywna_zmienna: f"{usun_polskie_znaki(krotka_nazwa)} ({konf.jednostka})"
        }, inplace=True)
        df_eksport.reset_index(drop=True, inplace=True)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.dataframe(df_eksport, use_container_width=True)

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')

            st.download_button(
                label="📥 Pobierz węzły modelu do Excela",
                data=csv_data,
                file_name=f"{parametr}_siatka_{str(data_modelu).replace(':', '').replace(' ', '_')}.csv",
                mime="text/csv"
            )