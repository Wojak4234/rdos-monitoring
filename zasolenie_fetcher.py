# zasolenie_fetcher.py

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

        # Warstwa WMS z SatBałtyku
        folium.raster_layers.WmsTileLayer(
            url="https://serwer-wms.satbaltyk.pl/geoserver/wms",
            layers="satbaltyk:salinity_surface",
            fmt="image/png",
            transparent=True,
            name="Zasolenie powierzchniowe [PSU]",
            attr="Dane: System SatBałtyk (IO PAN)"
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

    # Symulacja danych na potrzeby interfejsu
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
        * **Specyfika estuarium Odry:** Zalew Szczeciński jest środowiskiem przejściowym, w którym mieszają się wody słodkie z rzeki Odry (ok. 0.5 PSU) z wodami słonawymi z Morza Bałtyckiego (ok. 7 PSU w Zatoce Pomorskiej).
        * **Zjawisko cofki (Wlewy morskie):** Gwałtowne wzrosty zasolenia (piki na wykresach) występują najczęściej przy silnych, sztormowych wiatrach z kierunków północnych. Woda morska jest wtedy wpychana przez cieśniny (Świna, Dziwna) w głąb Zalewu.
        * **Teledekcja zasolenia:** Satelity nie mierzą bezpośrednio soli. Algorytmy SatBałtyk analizują właściwości optyczne wody, takie jak CDOM (żółta substancja rozpuszczona), która jest silnie skorelowana ze słodkimi wodami rzecznymi. 
        """)