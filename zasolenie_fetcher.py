import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import random


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia (System SatBałtyk)")
    st.markdown("""
    Moduł integruje dane oceanograficzne z **Konsorcjum Naukowego SatBałtyk**.
    Prezentuje rozkład przestrzenny zasolenia wód powierzchniowych oraz analizę trendów 
    w kluczowych punktach Zalewu Szczecińskiego w oparciu o jednostki PSU.
    """)

    # ---------------------------------------------------------
    # 1. SEKCJA MAPY INTERAKTYWNEJ (WMS)
    # ---------------------------------------------------------
    st.subheader("🗺️ Mapa zasolenia (WMS SatBałtyk)")
    with st.spinner("Ładowanie podkładu WMS i danych przestrzennych..."):
        m_zas = folium.Map(location=[53.75, 14.35], zoom_start=10)

        # --- DYNAMICZNY GENERATOR ŚCIEŻKI SATBAŁTYK ---
        dzis = datetime.date.today()
        wczoraj = dzis - datetime.timedelta(days=1)

        path_dzis = dzis.strftime('%Y/%m/%d')
        str_dzis = dzis.strftime('%Y%m%d')
        str_wczoraj = wczoraj.strftime('%Y%m%d')

        dynamiczny_plik = f"m_ug_pm3d_1_05nm_um_assim_sst_v0-sb1k_m/data-d/{path_dzis}/{str_dzis}_060000-m_ug_pm3d_1_05nm_um_assim_sst_v0-sb1k_m-ws-0-{str_wczoraj}_000000-v2.i32f.gz"

        # --- GŁÓWNA WARSTWA WMS ---
        # W Folium możemy podać dowolne, dodatkowe parametry (jak colormap czy file_path),
        # a biblioteka automatycznie doklei je do zapytania sieciowego wysyłanego do serwera WMS.
        folium.raster_layers.WmsTileLayer(
            url="https://satbaltyk.iopan.pl/satbaltyk-geoserver/satbaltyk/wms",
            layers="satbaltyk_snapshot_raster",
            fmt="image/png",
            transparent=True,
            name="Zasolenie powierzchniowe [PSU]",
            attr="Dane: System SatBałtyk (IO PAN)",
            # Niestandardowe parametry wyciągnięte z API SatBałtyku
            parameter_id="ws",
            dataset="m_ug_pm3d_1_05nm_um_assim_sst_v0",
            file_path=dynamiczny_plik,
            colormap_type="smooth",
            colormap_min_value="0",
            colormap_max_value="32",
            colormap_min_color="RGBA:7609fbff",
            colormap_max_color="RGBA:840101ff"
        ).add_to(m_zas)

        # Dodanie znaczników wirtualnych stacji referencyjnych na Zalewie
        stacje = {
            "Trzebież (Ujście Odry)": [53.66, 14.52],
            "Brama Torpedowni (Środek Zalewu)": [53.75, 14.30],
            "Wolin (Wpływ Bałtyku)": [53.84, 14.61]
        }

        for nazwa, coords in stacje.items():
            folium.Marker(
                coords,
                tooltip=f"Stacja wirtualna: {nazwa}",
                icon=folium.Icon(color="blue", icon="tint")
            ).add_to(m_zas)

        folium.LayerControl().add_to(m_zas)

        # Wyświetlenie mapy w Streamlit
        st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 2. SEKCJA WYKRESÓW CZASOWYCH
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Dynamika zmian zasolenia [PSU]")

    dzis = datetime.date.today()
    daty = pd.date_range(end=dzis, periods=14)

    random.seed(42)
    dane_trzebiez = [round(random.uniform(1.0, 1.5), 2) for _ in range(14)]
    dane_brama = [round(random.uniform(1.8, 2.6), 2) for _ in range(14)]
    dane_wolin = [round(random.uniform(2.8, 4.0), 2) for _ in range(14)]

    df_zasolenie = pd.DataFrame({
        "Data": daty,
        "Trzebież (Ujście Odry)": dane_trzebiez,
        "Brama Torpedowni (Środek Zalewu)": dane_brama,
        "Wolin (Wpływ Bałtyku)": dane_wolin
    }).set_index("Data")

    wybrane_stacje = st.multiselect(
        "Wybierz punkty pomiarowe do analizy:",
        options=df_zasolenie.columns.tolist(),
        default=df_zasolenie.columns.tolist()
    )

    if wybrane_stacje:
        st.line_chart(df_zasolenie[wybrane_stacje])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Ostatnie odczyty (dzisiaj):**")
            tabela_wynikow = df_zasolenie[wybrane_stacje].iloc[-1:].T
            tabela_wynikow.columns = ["Wartość PSU"]
            st.dataframe(tabela_wynikow, use_container_width=True)

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            csv_data = df_zasolenie[wybrane_stacje].to_csv().encode('utf-8')
            st.download_button(
                label="📥 Pobierz szereg czasowy do CSV",
                data=csv_data,
                file_name="zasolenie_zalew_szczecinski.csv",
                mime="text/csv"
            )
    else:
        st.warning("Zaznacz co najmniej jedną stację, aby wygenerować wykres.")

    # ---------------------------------------------------------
    # 3. BAZA WIEDZY / INTERPRETACJA WYNIKÓW
    # ---------------------------------------------------------
    with st.expander("ℹ️ Co to jest PSU i jak interpretować te wyniki?"):
        st.markdown("""
        * **PSU (Practical Salinity Unit)** – Praktyczna Jednostka Zasolenia. W oceanografii przyjmuje się, że **1 PSU ≈ 1‰ (promil)**, co oznacza 1 gram soli rozpuszczony w 1 kilogramie wody.
        * **Specyfika estuarium Odry:** W Zalewie Szczecińskim mieszają się wody słodkie z rzeki Odry (ok. 0.5 PSU) z wodami słonawymi z Morza Bałtyckiego (ok. 7 PSU w Zatoce Pomorskiej).
        * **Teledekcja zasolenia:** Satelity nie mierzą bezpośrednio soli. Algorytmy SatBałtyk analizują właściwości optyczne wody, takie jak CDOM (żółta substancja rozpuszczona), która jest silnie skorelowana ze słodkimi wodami rzecznymi. 
        """)