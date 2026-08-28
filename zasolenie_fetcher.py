import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests

def pobierz_surowe_dane(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Serwer zwrócił błąd: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Błąd połączenia: {e}")
        return None

def renderuj_modul_zasolenia():
    st.subheader("Bieżące zasolenie wód - Tylko Zalew Szczeciński")

    api_url = st.text_input(
        "Wklej ukryty adres URL z danymi JSON (z portalu badania.gios.gov.pl/odra/):",
        value=""
    )

    if api_url:
        with st.spinner("Pobieranie i filtrowanie przestrzenne danych..."):
            dane_json = pobierz_surowe_dane(api_url)

            if dane_json:
                try:
                    df = pd.json_normalize(dane_json)

                    kol_lat = next((c for c in df.columns if c.lower() in ['lat', 'latitude', 'gegrlat', 'szerokosc']), None)
                    kol_lon = next((c for c in df.columns if c.lower() in ['lon', 'lng', 'longitude', 'gegrlon', 'dlugosc']), None)

                    if kol_lat and kol_lon:
                        # 1. Konwersja współrzędnych na liczby zmiennoprzecinkowe
                        df[kol_lat] = df[kol_lat].astype(float)
                        df[kol_lon] = df[kol_lon].astype(float)

                        # 2. Bounding Box - współrzędne odcinające resztę kraju (Zalew Szczeciński)
                        maska_zalew = (
                                (df[kol_lat] >= 53.50) & (df[kol_lat] <= 53.95) &
                                (df[kol_lon] >= 14.10) & (df[kol_lon] <= 14.85)
                        )

                        # 3. Zastosowanie maski do ramki danych
                        df_zalew = df[maska_zalew].copy()

                        st.success(f"Filtrowanie zakończone. Znaleziono {len(df_zalew)} stacji pomiarowych na akwenie.")

                        if not df_zalew.empty:
                            st.write("### Tabela pomiarów (Zalew Szczeciński)")
                            st.dataframe(df_zalew, use_container_width=True)

                            st.write("### Lokalizacje stacji i odczyty")
                            m = folium.Map(location=[53.75, 14.4], zoom_start=10)

                            for idx, row in df_zalew.iterrows():
                                popup_html = "".join([f"<b>{k}:</b> {v}<br>" for k, v in row.items()])

                                folium.Marker(
                                    [row[kol_lat], row[kol_lon]],
                                    popup=folium.Popup(popup_html, max_width=300),
                                    icon=folium.Icon(color="darkblue", icon="tint")
                                ).add_to(m)

                            st_folium(m, width=1100, height=550, returned_objects=[])
                        else:
                            st.warning("Brak stacji w wyznaczonym obszarze. Upewnij się, że link zawiera dane dla całego kraju.")
                    else:
                        st.warning("Skrypt nie znalazł w danych kolumn ze współrzędnymi geograficznymi.")

                except Exception as e:
                    st.error(f"Błąd przetwarzania struktury JSON: {e}")
    else:
        st.info("Moduł oczekuje na wklejenie linku do źródła danych GIOŚ.")