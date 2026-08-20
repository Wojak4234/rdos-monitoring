# utils.py

def get_parameter_info(parameter):
    """Zwraca słownik z opisem i normami dla danego gazu."""
    info = {
        "NO2 (Dwutlenek azotu)": {
            "opis": "Gaz powstający głównie w wyniku spalania paliw w pojazdach silnikowych (szczególnie dieslach) oraz w elektrowniach. Działa drażniąco na drogi oddechowe.",
            "normy": "Satelita mierzy stężenie w kolumnie (mol/m²). Wartości na mapie powyżej **0.00005** oznaczają podwyższone zanieczyszczenie, a kolory wpadające w czerwień i fiolet (**> 0.0001**) to stan bardzo wysoki, mocno obciążający środowisko."
        },
        "SO2 (Dwutlenek siarki)": {
            "opis": "Powstaje głównie przy spalaniu zanieczyszczonego siarką węgla (energetyka i przemysł). Jest główną przyczyną kwaśnych deszczy.",
            "normy": "Wartości powyżej **0.0001 mol/m²** sygnalizują wyraźne źródła emisji przemysłowej (pomarańczowy). Poziomy **> 0.0003** (czerwony/fiolet) to zanieczyszczenie o charakterze ostrzegawczym."
        },
        "CO (Tlenek węgla)": {
            "opis": "Silnie trujący gaz (czad) pochodzący z niepełnego spalania paliw, m.in. w domowych piecach grzewczych, silnikach spalinowych oraz przy pożarach lasów.",
            "normy": "Kolumna **> 0.03 mol/m²** (żółty) to tło dla obszarów zurbanizowanych, natomiast **> 0.04 mol/m²** (czerwony) to obszary silnie zanieczyszczone (np. w intensywnym sezonie grzewczym)."
        },
        "Aerozole (Smog / Pyły)": {
            "opis": "Indeks UVAI (Absorbing Aerosol Index) wykrywa z kosmosu cząstki pochłaniające promieniowanie słoneczne, takie jak gęsty pył zawieszony (smog), dym z pożarów czy pył znad Sahary.",
            "normy": "Jest to indeks bezwymiarowy. Wartość **> 1.0** to zauważalne nagromadzenie pyłów/smogu, a **> 2.0** to bardzo intensywny epizod smogowy lub pożar, mocno ograniczający widoczność."
        }
    }
    return info.get(parameter, {})