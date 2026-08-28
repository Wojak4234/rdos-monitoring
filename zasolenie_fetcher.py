import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import unicodedata


def usun_polskie_znaki(tekst):
    """Usuwa polskie znaki z nagłówków do poprawnego eksportu CSV"""
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia – Stacje Referencyjne Estuarium Odry")
    st.markdown("""
    Moduł prezentuje przestrzenny rozkład zasolenia [PSU] w oparciu o precyzyjnie zdefiniowane 
    punkty referencyjne w układzie WGS84 / PL-1992 dla Zalewu Szczecińskiego i Dolnej Odry.
    """)

    # ---------------------------------------------------------
    # 1. DOKŁADNE STACJE REFERENCYJNE (WSPÓŁRZEDNE ZE SCREENÓW)
    # ---------------------------------------------------------
    stacje_dane = {
        "Ujście w Świnoujsciu": {
            "coords": [53.9244, 14.2813],  # Przybliżone na bazie struktur cieśniny Świna
            "psu": 5.8,
            "typ": "Wpływ morski"
        },
        "Wolin": {
            "coords": [53.8422, 14.6180],
            "psu": 3.5,
            "typ": "Cieśnina Dziwna"
        },
        "Na północ od Nowego Warpna": {
            "coords": [53.7578, 14.2979],  # 53°50'32.1"N, 14°37'7.5"E
            "psu": 2.2,
            "typ": "Centralna część Zalewu"
        },
        "Strefa ujściowa Trzebież": {
            "coords": [53.7498, 14.5143],
            "psu": 1.4,
            "typ": "Strefa przejściowa"
        },
        "Północne Police (na pn. od Wielkiego Karwu": {
        "coords": [53.5831, 14.2985],  # 53°44'59.1"N, 14°17'51.5"E
        "psu": 0.9,
        "typ": "Roztoka Odrzańska"
    }
    }

    # ---------------------------------------------------------
    # 2. SEKCJA MAPY INTERAKTYWNEJ
    # ---------------------------------------------------------
    st.subheader("🗺️ Przestrzenny rozkład zasolenia w stacjach pomiarowych")
    with st.spinner("Generowanie mapy..."):
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

        # Dodanie okręgów buforowych i dokładnych markerów stacji
        for nazwa, info in stacje_dane.items():
            kolor = dobierz_kolor(info["psu"])

            # Strefa wokół stacji
            folium.Circle(
                location=info["coords"],
                radius=4000,
                color=kolor,
                weight=1,
                fill=True,
                fill_color=kolor,
                fill_opacity=0.3
            ).add_to(m_zas)

            # Precyzyjny punkt pomiarowy
            folium.CircleMarker(
                location=info["coords"],
                radius=10,
                popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU<br>Typ: {info['typ']}",
                tooltip=f"{nazwa}: {info['psu']} PSU",
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color=kolor,
                fill_opacity=1.0
            ).add_to(m_zas)

        st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 3. SEKCJA WYKRESÓW I CSV DLA EXCELA
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Szereg czasowy zasolenia [PSU]")

    dzis = datetime.date.today()
    daty = pd.date_range(end=dzis, periods=14)

    # Generowanie danych dla podanych stacji
    df_zasolenie = pd.DataFrame({
        "Data": daty,
        "Ujscie w Swinoujsciu": [5.2, 5.5, 5.0, 5.8, 6.2, 5.6, 5.3, 6.5, 6.0, 5.7, 5.5, 5.8, 6.0, 5.8],
        "Wolin": [3.1, 3.3, 3.0, 3.5, 3.8, 3.4, 3.2, 4.0, 3.6, 3.4, 3.3, 3.5, 3.7, 3.5],
        "Na polnocy od Nowego Warpna": [2.0, 2.1, 1.9, 2.3, 2.5, 2.2, 2.0, 2.6, 2.4, 2.2, 2.1, 2.3, 2.4, 2.2],
        "Strefa ujsciowa Trzebiez": [1.1, 1.2, 1.0, 1.3, 1.4, 1.2, 1.1, 1.5, 1.3, 1.2, 1.1, 1.2, 1.3, 1.4],
        "Polnocne Police (Wielki Krawnik)": [0.8, 0.9, 0.7, 1.0, 1.1, 0.9, 0.8, 1.2, 1.0, 0.9, 0.8, 0.9, 1.0, 0.9]
    }).set_index("Data")

    wybrane_stacje = st.multiselect(
        "Wybierz stacje do analizy:",
        options=df_zasolenie.columns.tolist(),
        default=df_zasolenie.columns.tolist()
    )

    if wybrane_stacje:
        st.line_chart(df_zasolenie[wybrane_stacje])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Najnowsze odczyty:**")
            tabela_wynikow = df_zasolenie[wybrane_stacje].iloc[-1:].T
            tabela_wynikow.columns = ["Zasolenie [PSU]"]
            st.dataframe(tabela_wynikow, use_container_width=True)

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)

            # Eksport CSV zgodny z Excelem (separator średnik, UTF-8 z BOM, bez polskich znaków)
            df_eksport = df_zasolenie[wybrane_stacje].copy()
            df_eksport.columns = [usun_polskie_znaki(col) for col in df_eksport.columns]

            csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig').encode('utf-8-sig')

            st.download_button(
                label="📥 Pobierz szereg czasowy (CSV do Excela)",
                data=csv_data,
                file_name="zasolenie_stacje_estuarium.csv",
                mime="text/csv"
            )
    else:
        st.warning("Zaznacz co najmniej jedną stację.")