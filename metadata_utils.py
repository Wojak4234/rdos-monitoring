# metadata_utils.py

def get_parameter_info(key):
    """Słownik z pełnymi opisami parametrów atmosferycznych i wskaźników satelitarnych wraz z interpretacją wartości +/-."""
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
            "opis": "Normalized Difference Vegetation Index. Mierzy różnicę między bliską podczerwienią (NIR) a czerwienią (Red), wskazując na intensywność fotosyntezy i stan biomasy.",
            "normy": "Skala od -1 do 1.\n• **Wartości dodatnie (> 0 do 1)**: Oznaczają obecność i kondycję żywej roślinności (im wyższa wartość, tym gęstsza, zdrowsza i bardziej bujna zieleń).\n• **Wartości ujemne lub bliskie 0**: Wskazują na brak roślinności – wody otwarte, gołą glebę, skały, śnieg lub tereny zurbanizowane/zabudowane."
        },
        "NDWI (Woda / Mokradła)": {
            "opis": "Normalized Difference Water Index. Wykorzystuje pasma zielone i podczerwień do precyzyjnej detekcji powierzchni wodnych oraz wilgotności terenów.",
            "normy": "Skala od -1 do 1.\n• **Wartości dodatnie (> 0)**: Silnie wskazują na obecność wody stojącej, rzek, zbiorników wodnych lub podmokłych, nasyconych wodą terenów bagiennych.\n• **Wartości ujemne lub bliskie 0**: Oznaczają ląd suchy, glebę pozbawioną nadmiernej wilgoci lub zwartą pokrywę roślinną."
        },
        "NDMI (Wilgotność roślin)": {
            "opis": "Normalized Difference Moisture Index. Wykorzystuje pasma NIR i SWIR do oceny zawartości wody w tkankach roślinnych oraz stresu wodnego.",
            "normy": "Skala od -1 do 1.\n• **Wartości dodatnie**: Oznaczają wysoki poziom uwodnienia tkanek roślinnych oraz optymalne warunki wodne dla upraw i lasów.\n• **Wartości ujemne lub spadające w czasie**: Sygnalizują poważny stres wodny, deficyt wilgoci w glebie, suszę rolniczą lub zamieranie roślinności."
        },
        "Chlorofil-a (NDCI)": {
            "opis": "Normalized Difference Chlorophyll Index. Wskaźnik optyczny do monitorowania stężenia chlorofilu-a w wodach śródlądowych i przybrzeżnych.",
            "normy": "Skala od wartości ujemnych do dodatnich.\n• **Wartości dodatnie i rosnące**: Wskazują na wysokie stężenie chlorofilu, obecność fitoplanktonu oraz wysokie ryzyko wystąpienia zakwitów glonów lub sinic (zanieczyszczenie biogenami).\n• **Wartości ujemne lub bliskie zeru**: Oznaczają czystą wodę o niskiej zawartości materii organicznej i brak intensywnych zakwitów."
        }
    }
    return data.get(key, {"opis": "Brak opisu", "normy": "Brak danych"})