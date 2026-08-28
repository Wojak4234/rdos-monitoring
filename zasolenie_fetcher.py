import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import unicodedata


def usun_polskie_znaki(tekst):
    """Usuwa polskie znaki z nagłówków do eksportu CSV"""
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia – Model Wirtualnego Estuarium")
    st.markdown("""
    Autonomiczny moduł analityczny prezentujący rozkład przestrzenny i dynamikę zasolenia wód 
    w estuarium Odry i Zalewu Szczecińskiego w oparciu o zintegrowany model hydrodynamiczny.
    """)

    # ---------------------------------------------------------
    # 1. DANE POMIAROWE I STREFY PRZESTRZENNE
    # ---------------------------------------------------------
    stacje_dane = {
        "Widuchowa (Rzeka Odra - dopływ)": {
            "coords": [53.25, 14.45], "psu": 0.45, "typ": "Woda słodka"
        },
        "Trzebież (Ujście Odry)": {
            "coords": [53.66, 14.52], "psu": 1.25, "typ": "Woda przejściowa"
        },
        "Brama Torpedowni (Środek Zalewu)": {
            "coords": [53.75, 14.30], "psu": 2.20, "typ": "Woda słonawa"
        },
        "Roztoka Odrzańska": {
            "coords": [53.58, 14.58], "psu": 0.90, "typ": "Woda przejściowa"
        },
        "Wolin (Cieśnina Dziwna)": {
            "coords": [53.84, 14.61], "psu": 3.50, "typ": "Wpływ morski"
        },
        "Świnoujście (Cieśnina Świna)": {
            "coords": [53.91, 14.25], "psu": 5.80, "typ": "Wpływ morski"
        }
    }

    # ---------------------------------------------------------
    # 2. SEKCJA MAPY INTERAKTYWNEJ (KOLOROWE STREFY I STACJE)
    # ---------------------------------------------------------
    st.subheader("🗺️ Przestrzenny rozkład zasolenia [PSU]")
    with st.spinner("Generowanie mapy i stref zasolenia..."):
        m_zas = folium.Map(location=[53.70, 14.45], zoom_start=10, tiles="CartoDB positron")

        def dobierz_kolor(psu):
            if psu < 1.0:
                return "#2b83ba"  # Słodka (niebieski)
            elif psu < 2.5:
                return "#abdda4"  # Przejściowa (zielonkawy)
            elif psu < 4.5:
                return "#fdae61"  # Słonawa (pomarańczowy)
            else:
                return "#d7191c"  # Morska (czerwony)

        # Dodanie kolorowych okręgów strefowych (efekt plam/mapy cieplnej)
        strefy_wodne = [
            ([53.91, 14.25], 6000, 5.8, "Strefa wpływu morskiego (Świnoujście)"),
            ([53.84, 14.61], 5000, 3.5, "Strefa cieśniny Dziwna (Wolin)"),
            ([53.75, 14.30], 7000, 2.2, "Centralna część Zalewu Szczecińskiego"),
            ([53.66, 14.52], 5000, 1.25, "Strefa ujściowa Odry (Trzebież)"),
            ([53.58, 14.58], 4000, 0.9, "Roztoka Odrzańska"),
            ([53.25, 14.45], 8000, 0.45, "Koryto rzeki Odry (Widuchowa)")
        ]

        for coords, pr, psu_val, opis in strefy_wodne:
            kolor = dobierz_kolor(psu_val)
            folium.Circle(
                location=coords,
                radius=pr,
                popup=f"<b>{opis}</b><br>Średnie zasolenie: {psu_val} PSU",
                color=kolor,
                weight=1,
                fill=True,
                fill_color=kolor,
                fill_opacity=0.35  # Półprzezroczysta plama tworząca mapę cieplną
            ).add_to(m_zas)

        # Dodanie precyzyjnych markerów stacji na wierzchu
        for nazwa, info in stacje_dane.items():
            kolor = dobierz_kolor(info["psu"])
            folium.CircleMarker(
                location=info["coords"],
                radius=9,
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
    # 3. SEKCJA WYKRESÓW CZASOWYCH I EKSPORTU CSV
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Dynamika zmian zasolenia w stacjach pomiarowych")

    dzis = datetime.date.today()
    daty = pd.date_range(end=dzis, periods=14)

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

            # Przygotowanie danych CSV: oczyszczenie nagłówków z polskich znaków
            df_eksport = df_zasolenie[wybrane_stacje].copy()
            df_eksport.columns = [usun_polskie_znaki(col) for col in df_eksport.columns]

            # Kodowanie UTF-8 z BOM (bomsignal) oraz średnik jako separator (;),
            # dzięki czemu Excel automatycznie rozdzieli kolumny i poprawnie wyświetli plik.
            csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig').encode('utf-8-sig')

            st.download_button(
                label="📥 Pobierz szereg czasowy (CSV do Excela)",
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
        * **Gradient zasolenia:** Półprzezroczyste strefy na mapie odzwierciedlają przestrzenny rozkład gradientu zasolenia – od wód słodkich w południowej części Zalewu po silny wpływ morski w cieśninach.
        """)