import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import os
import unicodedata
import io
import base64
import requests
import copernicusmarine
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
from matplotlib.path import Path
from branca.element import Template, MacroElement


class ParamConfig:
    def __init__(self, nazwa: str, jednostka: str, cmap: str, legend_colors: list, dataset_id: str, typ_zmiennej: str):
        self.nazwa = nazwa
        self.jednostka = jednostka
        self.cmap = cmap
        self.legend_colors = legend_colors
        self.dataset_id = dataset_id
        self.typ_zmiennej = typ_zmiennej


KONFIGURACJA_PARAMETROW = {
    "so": ParamConfig(
        nazwa="Zasolenie wody",
        jednostka="PSU",
        cmap="jet",
        legend_colors=['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f', '#ffff00', '#ff7f00', '#ff0000',
                       '#7f0000'],
        dataset_id="cmems_mod_bal_phy_anfc_P1D-m",  # Zostawiamy stabilny Copernicus dla zasolenia
        typ_zmiennej="so"
    ),
    "zos": ParamConfig(
        nazwa="Stan wody na wodowskazach (IMGW)",
        jednostka="cm",
        cmap="coolwarm",
        legend_colors=['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43',
                       '#d73027'],
        dataset_id="IMGW_HYDRO_API",  # Leciutkie API IMGW zapobiegające wyciekom pamięci
        typ_zmiennej="poziom_wody_cm"
    )
}


def usun_polskie_znaki(tekst: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=1800)
def pobierz_wode_imgw():
    """Pobiera dane na żywo z IMGW i mapuje na współrzędne Zalewu bez obciążania RAM-u"""
    url = "https://danepubliczne.imgw.pl/api/data/hydro/"
    try:
        resp = requests.get(url, timeout=10)
        dane = resp.json()
    except Exception as e:
        st.error(f"Błąd połączenia z API IMGW: {e}")
        return None, None, "blad", None, None, None

    stacje_kordy = {
        "świnoujście": (53.906, 14.248),
        "dziwnów": (54.022, 14.743),
        "wolin": (53.841, 14.618),
        "trzebież": (53.605, 14.522),
        "stepnica": (53.651, 14.624),
        "most długi": (53.424, 14.560),  # Szczecin
        "podjuchy": (53.385, 14.588),  # Szczecin
        "gryfino": (53.251, 14.482),
        "widuchowa": (53.125, 14.385)
    }

    siatka_gradientu = []
    rows = []

    for d in dane:
        stacja_name = str(d.get("stacja", "")).lower()
        stan = d.get("stan_wody")
        if not stan: continue

        for key_name, coords in stacje_kordy.items():
            if key_name in stacja_name:
                stan_float = float(stan)
                siatka_gradientu.append({"lat": coords[0], "lon": coords[1], "wartosc": stan_float})
                rows.append({
                    'stacja': d.get("stacja"),
                    'latitude': coords[0],
                    'longitude': coords[1],
                    'poziom_wody_cm': stan_float
                })
                break

    df_grid_raw = pd.DataFrame(rows)
    if df_grid_raw.empty:
        return None, None, "blad", None, None, None

    maska_path = "zalew_maska.geojson"
    status_maski = "brak"
    zalew_gdf = None
    if os.path.exists(maska_path):
        status_maski = "zaladowana"
        zalew_gdf = gpd.read_file(maska_path).to_crs("EPSG:4326")

    data_odczytu = pd.Timestamp.now(tz='Europe/Warsaw').strftime("%Y-%m-%d %H:%M")
    return siatka_gradientu, data_odczytu, status_maski, zalew_gdf, df_grid_raw, "poziom_wody_cm"


@st.cache_data(ttl=3600)
def pobierz_stabilne_dane_copernicus(parametr: str = "so"):
    siatka_gradientu = []
    status_maski = "brak"
    zalew_gdf = None
    konf = KONFIGURACJA_PARAMETROW[parametr]

    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]
        ds = copernicusmarine.open_dataset(dataset_id=konf.dataset_id, username=user, password=pwd)

        dzisiaj = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
        ds_time = ds.sel(time=dzisiaj, method='nearest')

        # Wycinanie jeszcze PRZED wczytaniem wartości, aby zapobiec wyciekom RAM (OOM)
        sub = ds_time[konf.typ_zmiennej].sel(latitude=slice(53.40, 54.00), longitude=slice(14.15, 14.80))

        try:
            sub = sub.isel(depth=0)
        except Exception:
            pass

        lats = sub.latitude.values
        lons = sub.longitude.values
        vals = sub.values

        rows = []
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                v = vals[i, j] if vals.ndim == 2 else vals.item()
                if not np.isnan(v):
                    rows.append({'latitude': float(lat), 'longitude': float(lon), konf.typ_zmiennej: float(v)})

        df_grid_raw = pd.DataFrame(rows)
        if df_grid_raw.empty:
            return None, None, "blad", None, None, None

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
                "lat": row['latitude'], "lon": row['longitude'], "wartosc": row[konf.typ_zmiennej]
            })

        data_odczytu = str(ds_time.time.values)[:16].replace("T", " ")
        return siatka_gradientu, data_odczytu, status_maski, zalew_gdf, df_do_mapy, konf.typ_zmiennej
    except Exception as e:
        st.error(f"Błąd pobierania danych z Copernicusa: {e}")
        return None, None, "blad", None, None, None


@st.cache_data(ttl=86400)
def pobierz_szereg_czasowy_30_dni(parametr: str = "so"):
    konf = KONFIGURACJA_PARAMETROW[parametr]
    if konf.dataset_id == "IMGW_HYDRO_API":
        return None  # IMGW z tego endpointu daje tylko "teraz", bez pełnej historii

    try:
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]
        ds = copernicusmarine.open_dataset(dataset_id=konf.dataset_id, username=user, password=pwd)

        dzisiaj = pd.Timestamp.now(tz='UTC').replace(tzinfo=None)
        trzydziesci_dni_temu = dzisiaj - pd.Timedelta(days=30)

        ostatnie_30 = ds.sel(time=slice(trzydziesci_dni_temu, dzisiaj))
        sub_ds = ostatnie_30[konf.typ_zmiennej].sel(latitude=slice(53.40, 54.00), longitude=slice(14.15, 14.80))
        try:
            sub_ds = sub_ds.isel(depth=0)
        except Exception:
            pass

        mean_series = sub_ds.mean(dim=['latitude', 'longitude'], skipna=True)
        szereg = pd.DataFrame(
            {'Data': pd.to_datetime(mean_series.time.values), f"Średnia ({konf.jednostka})": mean_series.values})
        szereg['Data'] = szereg['Data'].dt.date
        return szereg.dropna()
    except Exception:
        return None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Hydrofizyczne (Hybrydowe: CMEMS & IMGW)")

    wybrany_parametr_opcja = st.radio(
        "Wybierz parametr przestrzenny do analizy:",
        options=["Zasolenie wody", "Wysokość lustra wody (Podtopienia/Przejezdność)"],
        horizontal=True
    )

    if "Zasolenie" in wybrany_parametr_opcja:
        parametr = "so"
    else:
        parametr = "zos"

    konf = KONFIGURACJA_PARAMETROW[parametr]

    with st.spinner(f"Odpytuję źródła danych dla parametru: {konf.nazwa}..."):
        if konf.dataset_id == "IMGW_HYDRO_API":
            siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle, aktywna_zmienna = pobierz_wode_imgw()
        else:
            siatka_gradientu, data_modelu, status_maski, zalew_gdf, df_piksle, aktywna_zmienna = pobierz_stabilne_dane_copernicus(
                parametr)

    if not siatka_gradientu:
        st.warning("Pobieranie przerwane. Sprawdź połączenie ze źródłami lub poświadczenia.")
        return

    vals_array = np.array([p["wartosc"] for p in siatka_gradientu])
    val_min, val_max, val_mean = float(vals_array.min()), float(vals_array.max()), float(vals_array.mean())
    st.success(f"✅ Przestrzenny model '{konf.nazwa}' pobrany pomyślnie. Moduł całkowicie odporny na przeciążenia.")

    st.info(f"📅 **Stan faktyczny na:** {data_modelu}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Minimalny wynik", f"{val_min:.2f} {konf.jednostka}")
    c2.metric("Średni wynik", f"{val_mean:.2f} {konf.jednostka}")
    c3.metric("Maksymalny wynik", f"{val_max:.2f} {konf.jednostka}")

    st.subheader(f"🗺️ Mapa przestrzenna: {konf.nazwa}")

    try:
        m_zas = folium.Map(location=(53.75, 14.45), zoom_start=10, tiles="OpenStreetMap")

        if len(siatka_gradientu) >= 3:
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
                    stacja_info = f" ({row['stacja']})" if 'stacja' in row else ""
                    folium.CircleMarker(
                        location=(row['latitude'], row['longitude']),
                        radius=10,
                        color='black',
                        fill=True,
                        fill_color='white',
                        fill_opacity=0.7,
                        tooltip=f"Odczyt{stacja_info}: <br><b>{row[aktywna_zmienna]:.2f} {konf.jednostka}</b>"
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
                    <span>{val_max:.1f}</span>
                    <span>{val_min + (val_max - val_min) * 0.75:.1f}</span>
                    <span>{val_min + (val_max - val_min) * 0.5:.1f}</span>
                    <span>{val_min + (val_max - val_min) * 0.25:.1f}</span>
                    <span>{val_min:.1f}</span>
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
        st.warning(f"Błąd renderowania mapy: {e}")

    st.markdown("---")
    st.subheader(f"📈 Dynamika zmian - {konf.nazwa} (Ostatnie 30 dni)")
    try:
        with st.spinner("Pobieranie historii..."):
            szereg_df = pobierz_szereg_czasowy_30_dni(parametr)
        if szereg_df is not None and not szereg_df.empty:
            st.line_chart(szereg_df.set_index('Data'), color="#007fff" if parametr == "so" else "#e31a1c")
        else:
            st.info(
                "Brak danych historycznych z darmowego publicznego API IMGW na tym widoku (dostępny tylko odczyt na żywo).")
    except Exception:
        st.info("Wykres historyczny niedostępny.")

    st.markdown("---")
    st.subheader("📊 Tabela danych przestrzennych (Eksport Excel)")

    if aktywna_zmienna is not None:
        try:
            # Tworzenie czystej ramki danych do eksportu
            if 'stacja' in df_piksle.columns:
                df_eksport = df_piksle[['stacja', 'latitude', 'longitude', aktywna_zmienna]].copy()
            else:
                df_eksport = df_piksle[['latitude', 'longitude', aktywna_zmienna]].copy()

            df_eksport.rename(columns={
                'stacja': 'Nazwa Stacji (IMGW)',
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
                    label="📥 Pobierz węzły/stacje do Excela",
                    data=csv_data,
                    file_name=f"{parametr}_siatka_eksport.csv",
                    mime="text/csv"
                )
        except Exception:
            st.warning("Tabela tymczasowo niedostępna.")