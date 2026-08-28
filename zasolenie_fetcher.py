import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import unicodedata
import xarray as xr
import copernicusmarine


def usun_polskie_znaki(tekst):
    """Usuwa polskie znaki z nagłówków do poprawnego eksportu CSV"""
    nfkd_form = unicodedata.normalize('NFKD', tekst)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


@st.cache_data(ttl=86400)  # Odpytuje API maksymalnie raz na 24 godziny
def pobierz_rzeczywiste_zasolenie():
    """Pobiera aktualne zasolenie (PSU) z modelu numerycznego Bałtyku (Copernicus)"""
    stacje_definicje = {
        "Ujście w Świnoujsciu": {"coords": [53.9244, 14.2813], "typ": "Wpływ morski"},
        "Wolin": {"coords": [53.8422, 14.6180], "typ": "Cieśnina Dziwna"},
        "Na północ od Nowego Warpna": {"coords": [53.7578, 14.2979], "typ": "Centralna część Zalewu"},
        "Strefa ujściowa Trzebież": {"coords": [53.7498, 14.5143], "typ": "Strefa przejściowa"},
        "Północne Police (Wielki Krawnik)": {"coords": [53.5831, 14.2985], "typ": "Roztoka Odrzańska"}
    }

    wyniki = {}

    try:
        # Pobranie poświadczeń z bezpiecznych sekretów Streamlita
        user = st.secrets["copernicus"]["username"]
        pwd = st.secrets["copernicus"]["password"]

        # Otwarcie zbioru danych w locie bez pobierania ogromnego pliku (NetCDF przez OPeNDAP)
        # cmems_mod_bal_phy_anfc_P1D-m to model fizyczny Bałtyku (średnie dzienne)
        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_bal_phy_anfc_P1D-m",
            username=user,
            password=pwd
        )

        # Pobranie danych dla najnowszej dostępnej daty (zazwyczaj dzisiaj/wczoraj)
        ostatni_czas = ds.isel(time=-1)

        for nazwa, info in stacje_definicje.items():
            lat = info["coords"][0]
            lon = info["coords"][1]

            # Ekstrakcja najbliższego mokrego piksela dla warstwy powierzchniowej (depth=0)
            # so = Salinity (zasolenie)
            wartosc_so = ostatni_czas['so'].sel(lat=lat, lon=lon, method='nearest').isel(depth=0).values

            wyniki[nazwa] = {
                "coords": info["coords"],
                "typ": info["typ"],
                "psu": round(float(wartosc_so), 2)
            }

        return wyniki, str(ostatni_czas.time.values)[:10]  # Zwraca wyniki i datę modelu

    except Exception as e:
        # W razie awarii API lub braku konta wypluwa błąd inżynierski, ale nie wysypuje całej strony
        st.error(f"⚠️ Błąd połączenia z API Copernicus Marine: {e}")
        return None, None


def renderuj_modul_zasolenia():
    st.header("🌊 Monitorowanie Zasolenia (Dane Rzeczywiste Copernicus CMEMS)")
    st.markdown("""
    Moduł prezentuje aktualny przestrzenny rozkład zasolenia [PSU] na podstawie asymilacji 
    satelitarnych i in-situ z modelu numerycznego Bałtyku.
    """)

    with st.spinner("Nawiązywanie połączenia z systemem Copernicus (OPeNDAP)..."):
        dane_rzeczywiste, data_modelu = pobierz_rzeczywiste_zasolenie()

    if not dane_rzeczywiste:
        st.warning("Uzupełnij klucze API w st.secrets, aby pobrać dane.")
        return

    st.success(f"✅ Pomyślnie pobrano najświeższe dane referencyjne dla estuarium (Data modelu: {data_modelu})")

    # ---------------------------------------------------------
    # 1. SEKCJA MAPY INTERAKTYWNEJ (Oparta w 100% na danych pobranych)
    # ---------------------------------------------------------
    st.subheader("🗺️ Przestrzenny rozkład zasolenia w stacjach pomiarowych")
    m_zas = folium.Map(location=[53.75, 14.45], zoom_start=10, tiles="CartoDB positron")

    def dobierz_kolor(psu):
        if psu < 1.0:
            return "#2b83ba"
        elif psu < 2.5:
            return "#abdda4"
        elif psu < 4.5:
            return "#fdae61"
        else:
            return "#d7191c"

    for nazwa, info in dane_rzeczywiste.items():
        kolor = dobierz_kolor(info["psu"])

        folium.Circle(
            location=info["coords"], radius=4000,
            color=kolor, weight=1, fill=True, fill_color=kolor, fill_opacity=0.3
        ).add_to(m_zas)

        folium.CircleMarker(
            location=info["coords"], radius=10,
            popup=f"<b>{nazwa}</b><br>Zasolenie: {info['psu']} PSU<br>Typ: {info['typ']}",
            tooltip=f"{nazwa}: {info['psu']} PSU",
            color="#ffffff", weight=2, fill=True, fill_color=kolor, fill_opacity=1.0
        ).add_to(m_zas)

    st_folium(m_zas, width=1100, height=500, returned_objects=[])

    # ---------------------------------------------------------
    # 2. SEKCJA BIEŻĄCYCH WYNIKÓW I EKSPORTU (Z formatowaniem dla Excela)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Aktualne odczyty hydrofizyczne (PSU)")

    # Transformacja słownika na ładny DataFrame dla Streamlita
    df_wyniki = pd.DataFrame.from_dict(dane_rzeczywiste, orient='index')
    df_wyniki.index.name = "Stacja"
    df_wyniki.reset_index(inplace=True)
    df_wykres = df_wyniki[['Stacja', 'psu']].set_index('Stacja').T

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(df_wyniki[['Stacja', 'typ', 'psu']], use_container_width=True)

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)

        # Formatowanie CSV dokładnie pod excela (brak krzaków)
        df_eksport = df_wyniki.copy()
        df_eksport.columns = [usun_polskie_znaki(col) for col in df_eksport.columns]
        df_eksport['Stacja'] = df_eksport['Stacja'].apply(usun_polskie_znaki)

        csv_data = df_eksport.to_csv(sep=';', encoding='utf-8-sig', index=False).encode('utf-8-sig')

        st.download_button(
            label="📥 Pobierz dzisiejszy stan zasolenia (CSV do Excela)",
            data=csv_data,
            file_name=f"zasolenie_estuarium_{data_modelu}.csv",
            mime="text/csv"
        )