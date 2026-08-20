# metadata_utils.py

def get_parameter_info(key):
    """Słownik z pełnymi opisami parametrów atmosferycznych i wskaźników satelitarnych."""
    data = {
        "NO2 (Dwutlenek azotu)": {
            "opis": "Gaz powstający głównie w wyniku spalania paliw w pojazdach silnikowych (szczególnie dieslach) oraz w elektrowniach. Działa drażniąco na drogi oddechowe.",
            "normy": "Satelita mierzy stężenie w kolumnie (mol/m²). Wartości na mapie powyżej **0.00005** oznaczają podwyższone zanieczyszczenie, a kolory wpadające w czerwień i fiolet (**> 0.0001**) to stan bardzo wysoki."
        },
        "SO2 (Dwutlenek siarki)": {
            "opis": "Powstaje głównie przy spalaniu zanieczyszczonego siarką węgla (energetyka i przemysł). Jest główną przyczyną kwaśnych deszczy.",
            "normy": "Wartości powyżej **0.0001 mol/m²** sygnalizują wyraźne źródła emisji przemysłowej (pomarańczowy). Poziomy **> 0.0003** (czerwony/fiolet) to zanieczyszczenie ostrzegawcze."
        },
        "CO (Tlenek węgla)": {
            "opis": "Silnie trujący gaz (czad) pochodzący z niepełnego spalania paliw, m.in. w domowych piecach grzewczych, silnikach spalinowych oraz przy pożarach lasów.",
            "normy": "Kolumna **> 0.03 mol/m²** (żółty) to tło dla obszarów zurbanizowanych, natomiast **> 0.04 mol/m²** (czerwony) to obszary silnie zanieczyszczone."
        },
        "Aerozole (Smog / Pyły)": {
            "opis": "Indeks UVAI (Absorbing Aerosol Index) wykrywa z kosmosu cząstki pochłaniające promieniowanie słoneczne, takie jak gęsty pył zawieszony (smog), dym z pożarów czy pył znad Sahary.",
            "normy": "Jest to indeks bezwymiarowy. Wartość **> 1.0** to zauważalne nagromadzenie pyłów/smogu, a **> 2.0** to bardzo intensywny epizod smogowy lub pożar, mocno ograniczający widoczność."
        },
        "NDVI (Wegetacja)": {
            "opis": "Normalized Difference Vegetation Index. Mierzy różnicę między bliską podczerwienią (NIR) a czerwienią (Red), wskazując na intensywność fotosyntezy.",
            "normy": "Wartości powyżej 0.5 oznaczają gęstą, zdrową roślinność. Niskie/ujemne = woda, zabudowa, gleba."
        },
        "NDWI (Woda / Mokradła)": {
            "opis": "Normalized Difference Water Index. Wykorzystuje pasma zielone i NIR do detekcji powierzchni wodnych.",
            "normy": "Wartości dodatnie (>0) wskazują na obecność wody lub terenów podmokłych."
        },
        "NDMI (Wilgotność roślin)": {
            "opis": "Normalized Difference Moisture Index. Wykorzystuje NIR i SWIR do oceny zawartości wody w tkankach roślinnych.",
            "normy": "Pozwala wykryć stres wodny upraw lub lasów. Spadek wartości w czasie sugeruje suszę."
        },
        "Chlorofil-a (NDCI)": {
            "opis": "Normalized Difference Chlorophyll Index. Wskaźnik optyczny do monitorowania stężenia chlorofilu-a w wodach śródlądowych.",
            "normy": "Wysokie wartości wskazują na intensywne zakwity glonów lub sinic, często świadcząc o zanieczyszczeniu wód biogenami."
        }
    }
    return data.get(key, {"opis": "Brak danych", "normy": "Brak danych"})