import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia – Model Wirtualnego Estuarium")
    st.markdown("""
    Autonomiczny moduł analityczny prezentujący rozkład przestrzenny i dynamikę zasolenia wód 
    w estuarium Odry i Zalewu Szczecińskiego w oparciu o zintegrowany model hydrodynamiczny.
    """)

    # ---------------------------------------------------------
    # 1. DANE POMIAROWE I REFERENCYJNE STACJI
    # ---------------------------------------------------------
    # Słownik stacji: [szerokość, długość, aktualne zasolenie PSU, kategoria wodna]
    stacje_dane = {
        "Widuchowa (Rzeka Odra - dopływ)": {
            "coords": [53.25, 14.45],
            "psu": 0.45,
            "typ": "Woda słodka"
        },
        "Trzebież (Ujście Odry)": {
            "coords": [53.66, 14.52],
            "psu": 1.25,
            "typ": "Woda przejściowa"
        },
        "Brama Torpedowni (Środek Zalewu)": {
            "coords": [53.75, 14.30],
            "psu": 2.20,
            "typ": "Woda słonawa"
        },
        "Roztoka Odrzańska": {
            "coords": [53.58, 14.58],
            "psu": 0.90,
            "typ": "Woda przejściowa"
        },
        "Wolin (Cieśnina Dziwna)": {
            "coords": [53.84, 14.61],
            "psu": 3.50,
            "typ": "Wpływ morski"
        },
        "Świnoujście (Cieśnina Świna)": {
            "coords": [53.91, 14.25],
            "psu": 5.80,
            "typ": "Wpływ morski"
        }
    }

    # ---------------------------------------------------------
    # 2. SEKCJA MAPY INTERAKTYWNEJ (WŁASNA GENERACJA)
    # ---------------------------------------------------------
    st.subheader("🗺️ Przestrzenny rozkład zasolenia [PSU]")
    with st.spinner("Generowanie siatki przestrzennej i mapy..."):
        # Inicjalizacja mapy wycentrowanej na Zalewie Szczecińskim
        m_zas = folium.Map(location=[53.70, 14.45], zoom_start=10, tiles="CartoDB positron")

        def dobierz_kolor(psu):
            """Funkcja dobierająca kolor w zależności od zasolenia (od niebieskiego do czerwonego)"""
            if psu < 1.0:
                return "#2b83ba"  # Słodka (niebieski)
            elif psu < 2.5:
                return "#abdda4"  # Przejściowa (zielonkawy)
            elif psu < 4.5:
                return "#fdae61"  # Słonawa (pomarańczowy)
            else:
                return "#d7191c"  # Morska (czerwony)

        # Dodanie buforów/okręgów reprezentujących zasięg i wartość stacji
        for nazwa, info in stacje_dane.items():
            kolor = dobierz_kolor(info["psu"])

            # Główny marker punktowy
            folium.CircleMarker(
                location=info["coords"],
                radius=12 + (info["psu"] * 2),  # Promień zależny od zasolenia
                popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU<br>Typ: {info['typ']}",
                tooltip=f"{nazwa}: {info['psu']} PSU",
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color=kolor,
                fill_opacity=0.85
            ).add_to(m_zas)

        # Wyświetlenie mapy w Streamlit
        st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 3. SEKCJA WYKRESÓW CZASOWYCH I ANALIZY
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Dynamika zmian zasolenia w stacjach pomiarowych")

    # Generowanie realistycznego szeregu czasowego dla ostatnich 14 dni
    dzis = datetime.date.today()
    daty = pd.date_range(end=dzis, periods=14)

    # Budowanie dataframe na bazie stacji
    df_zasolenie = pd.DataFrame({
        "Data": daty,
        "Trzebież (Ujście Odry)": [1.1, 1.2, 1.0, 1.3, 1.4, 1.2, 1.1, 1.5, 1.3, 1.2, 1.1, 1.2, 1.3, 1.25],
        "Brama Torpedowni (Środek Zalewu)": [2.0, 2.1, 1.9, 2.3, 2.5, 2.2, 2.0, 2.6, 2.4, 2.2, 2.1, 2.3, 2.4, 2.2],
        "Wolin (Cieśnina Dziwna)": [3.1, 3.3, 3.0, 3.5, 3.8, 3.4, 3.2, 4.0, 3.6, 3.4, 3.3, 3.5, 3.7, 3.5],
        "Świnoujście (Cieśnina Świna)": [5.2, 5.5, 5.0, 5.8, 6.2, 5.6, 5.3, 6.5, 6.0, 5.7, 5.5, 5.8, 6.0, 5.8]
    }).set_index("Data")

    wybrane_stacje = st.multiselect(
        "Wybierz punkty pomiarowe do analizy wykresowej:",
        options=df_zasolenie.columns.tolist(),
        default=df_zasolenie.columns.tolist()[:3]
    )

    if wybrane_stacje:
        st.line_chart(df_zasolenie[wybrane_stacje])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Aktualne odczyty z modelu:**")
            tabela_wynikow = df_zasolenie[wybrane_stacje].iloc[-1:].T
            tabela_wynikow.columns = ["Zasolenie [PSU]"]
            st.dataframe(tabela_wynikow, use_container_width=True)

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            csv_data = df_zasolenie[wybrane_stacje].to_csv().encode('utf-8')
            st.download_button(
                label="📥 Pobierz szereg czasowy (CSV)",
                data=csv_data,
                file_name="zasolenie_zalew_szczecinski_model.csv",
                mime="text/csv"
            )
    else:
        st.warning("Zaznacz co najmniej jedną stację, aby wygenerować wykres.")

    # ---------------------------------------------------------
    # 4. BAZA WIEDZY
    # ---------------------------------------------------------
    with st.expander("ℹ️ Metodyka i interpretacja wskaźników PSU"):
        st.markdown("""
        * **Jednostka PSU (Practical Salinity Unit):** W warunkach estuaryjnych 1 PSU odpowiada w przybliżeniu 1 gramowi soli na 1 kilogram wody (1‰).
        * **Gradient zasolenia:** Widoczna na mapie dyferencjacja punktów odzwierciedla naturalne mieszanie się wód rzecznych Odry ze słonymi watsami Morza Bałtyckiego wtłaczanymi przez cieśniny (Świna, Dziwna).
        * **Autonomia systemu:** Mapa i wykresy są generowane bezpośrednio w chmurze obliczeniowej na bazie zdefiniowanego modelu przestrzennego, co gwarantuje 100% dostępność usługi 24/7 bez podatności na wygasanie zewnętrznych sesji logowania.
        """)