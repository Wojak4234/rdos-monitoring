import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium


@st.cache_data(ttl=3600)
def pobierz_dane_zasolenia():
    # Tutaj w przyszłości wepniemy prawdziwy endpoint API GIOŚ/IMGW
    # Na ten moment używamy danych testowych, żeby ułożyć interfejs
    dane_testowe = [
        {"nazwa": "Stacja Trzebież", "lat": 53.66, "lon": 14.52, "przewodnosc_uS": 1250, "status": "W normie"},
        {"nazwa": "Stacja Wolin", "lat": 53.84, "lon": 14.61, "przewodnosc_uS": 1800, "status": "Podwyższone"}
    ]
    return pd.DataFrame(dane_testowe)


def renderuj_modul_zasolenia():
    st.subheader("Bieżące parametry: Zalew Szczeciński i dolna Odra")

    df = pobierz_dane_zasolenia()

    if not df.empty:
        st.dataframe(df, use_container_width=True)

        st.write("**Rozkład przestrzenny przewodności elektrolitycznej (zasolenia)**")

        # Wyśrodkowanie na Zalewie
        m = folium.Map(location=[53.75, 14.30], zoom_start=9)

        for idx, row in df.iterrows():
            kolor = "green" if row['przewodnosc_uS'] < 1500 else "orange"

            folium.Marker(
                [row['lat'], row['lon']],
                popup=f"<b>{row['nazwa']}</b><br>Przewodność: {row['przewodnosc_uS']} µS/cm",
                icon=folium.Icon(color=kolor, icon="tint")
            ).add_to(m)

        st_folium(m, width=700, height=500)
    else:
        st.info("Brak danych o zasoleniu do wyświetlenia.")