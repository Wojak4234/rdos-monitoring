# metadata_utils.py

def get_parameter_info(key):
    """
    Zwraca słownik z opisem, interpretacją i normami dla parametrów atmosferycznych oraz wskaźników satelitarnych.
    """
    data = {
        # --- ATMOSFERA ---
        "NO2 (Dwutlenek azotu)": {
            "opis": "Gaz powstający głównie w wyniku spalania paliw w pojazdach silnikowych (szczególnie dieslach) oraz w elektrowniach. Działa drażniąco na drogi oddechowe.",
            "normy": "Satelita mierzy stężenie w kolumnie (mol/m²). Wartości na mapie powyżej **0.00005** oznaczają podwyższone zanieczyszczenie, a **> 0.0001** to stan bardzo wysoki."
        },
        "SO2 (Dwutlenek siarki)": {
            "opis": "Powstaje głównie przy spalaniu zanieczyszczonego siarką węgla (energetyka i przemysł). Główna przyczyna kwaśnych deszczy.",
            "normy": "Wartości powyżej **0.0001 mol/m²** sygnalizują źródła emisji przemysłowej. Poziomy **> 0.0003** to zanieczyszczenie ostrzegawcze."
        },
        "CO (Tlenek węgla)": {
            "opis": "Silnie trujący gaz (czad) pochodzący z niepełnego spalania paliw (piece grzewcze, silniki).",
            "normy": "Kolumna **> 0.03 mol/m²** to tło zurbanizowane, **> 0.04 mol/m²** to obszary silnie zanieczyszczone."
        },
        "Aerozole (Smog / Pyły)": {
            "opis": "Indeks UVAI wykrywa z kosmosu cząstki pochłaniające światło (smog, dym, pył znad Sahary).",
            "normy": "Indeks bezwymiarowy. Wartość **> 1.0** to smog, **> 2.0** to intensywny epizod lub pożar."
        },

        # --- WEGETACJA I WODA ---
        "NDVI (Wegetacja)": {
            "opis": "Normalized Difference Vegetation Index. Mierzy różnicę między bliską podczerwienią (NIR) a czerwienią (Red), wskazując na intensywność fotosyntezy.",
            "interpretacja": "Skala -1 do 1. Wysokie wartości (>0.5) = gęsta, zdrowa roślinność. Niskie/ujemne = woda, zabudowa, gleba bez roślin."
        },
        "NDWI (Woda / Mokradła)": {
            "opis": "Normalized Difference Water Index. Wykorzystuje pasma zielone i NIR do detekcji powierzchni wodnych.",
            "interpretacja": "Wartości dodatnie (>0) silnie wskazują na obecność wody lub terenów podmokłych. Im wyższa wartość, tym czystsza/głębsza woda."
        },
        "NDMI (Wilgotność roślin)": {
            "opis": "Normalized Difference Moisture Index. Wykorzystuje NIR i SWIR do oceny zawartości wody w tkankach roślinnych.",
            "interpretacja": "Pozwala wykryć wczesne stadia suszy roślinnej. Spadek wartości w czasie jest sygnałem stresu wodnego upraw lub lasów."
        },
        "Chlorofil-a (NDCI)": {
            "opis": "Normalized Difference Chlorophyll Index. Wskaźnik optyczny do monitorowania stężenia chlorofilu-a w wodach śródlądowych.",
            "interpretacja": "Wysokie wartości wskazują na intensywne zakwity glonów lub sinic, co często świadczy o zanieczyszczeniu wód biogenami."
        }
    }
    return data.get(key, {"opis": "Brak opisu", "normy": "Brak danych"})