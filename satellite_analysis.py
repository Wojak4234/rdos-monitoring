import ee
import pandas as pd
import datetime
import requests
import urllib.parse


def calculate_index_time_series(geojson_feature, index_type, start_date, end_date):
    try:
        roi = ee.Geometry(geojson_feature['geometry'])

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(roi) \
            .filterDate(str(start_date), str(end_date)) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25))

        def process_image(img):
            if index_type == "NDVI (Wegetacja)":
                layer = img.normalizedDifference(['B8', 'B4']).rename('INDEX')
            elif index_type == "NDWI (Woda / Mokradła)":
                layer = img.normalizedDifference(['B3', 'B8']).rename('INDEX')
            elif index_type == "NDMI (Wilgotność roślin)":
                layer = img.normalizedDifference(['B8', 'B11']).rename('INDEX')
            else:
                layer = img.normalizedDifference(['B8', 'B4']).rename('INDEX')

            date_str = img.date().format('YYYY-MM-dd')
            mean_dict = layer.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=30,
                maxPixels=1e8
            )
            return ee.Feature(None, {'date': date_str, 'VAL': mean_dict.get('INDEX')})

        ts_collection = s2.map(process_image)
        info = ts_collection.getInfo()

        data = []
        for feat in info.get('features', []):
            props = feat['properties']
            d = props.get('date')
            val = props.get('VAL')
            if d and val is not None:
                data.append({'date': d, 'Wartość': val})

        if not data:
            return None

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
        return df[['Wartość']]

    except Exception as e:
        print(f"Błąd szeregu czasowego wskaźnika: {e}")
        return None


def get_available_dates(parameter, days_back=90):
    try:
        if parameter == "NO2 (Dwutlenek azotu)":
            col = 'L3_NO2'
        elif parameter == "SO2 (Dwutlenek siarki)":
            col = 'L3_SO2'
        elif parameter == "CO (Tlenek węgla)":
            col = 'L3_CO'
        elif parameter == "Aerozole (Smog / Pyły)":
            col = 'L3_AER_AI'
        else:
            return []

        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        point = ee.Geometry.Point([15.6, 53.6])

        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(str(start_date), str(end_date)) \
            .filterBounds(point)

        times = s5p.aggregate_array('system:time_start').getInfo()

        if not times:
            return []

        dates = pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
        dates.sort(reverse=True)
        return dates

    except Exception as e:
        raise Exception(f"Błąd GEE: {str(e)}")


def get_atmospheric_layer(target_date, parameter):
    try:
        start = ee.Date(target_date)
        end = start.advance(1, 'day')

        if parameter == "NO2 (Dwutlenek azotu)":
            col, band, threshold, max_val = 'L3_NO2', 'tropospheric_NO2_column_number_density', 0.00002, 0.0001
        elif parameter == "SO2 (Dwutlenek siarki)":
            col, band, threshold, max_val = 'L3_SO2', 'SO2_column_number_density', 0.00001, 0.0005
        elif parameter == "CO (Tlenek węgla)":
            col, band, threshold, max_val = 'L3_CO', 'CO_column_number_density', 0.02, 0.05
        elif parameter == "Aerozole (Smog / Pyły)":
            col, band, threshold, max_val = 'L3_AER_AI', 'absorbing_aerosol_index', 0.1, 2.0
        else:
            return None, None, None

        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(start, end) \
            .select(band) \
            .mean()

        s5p_high = s5p.updateMask(s5p.gt(threshold))

        viz = {'min': threshold, 'max': max_val, 'palette': ['yellow', 'orange', 'red', 'purple']}
        map_id_dict = s5p_high.getMapId(viz)

        return map_id_dict['tile_fetcher'].url_format, threshold, max_val
    except Exception as e:
        raise Exception(f"Błąd GEE: {str(e)}")


def get_parameter_info(parameter):
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


def get_s2_water_dates(days_back=90):
    try:
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        point = ee.Geometry.Point([14.4, 53.7])

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(point) \
            .filterDate(str(start_date), str(end_date)) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))

        times = s2.aggregate_array('system:time_start').getInfo()

        if not times:
            return []

        dates = pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
        dates.sort(reverse=True)
        return dates
    except Exception as e:
        raise Exception(f"Błąd GEE (S2 Water Dates): {str(e)}")


def get_water_quality_layer(target_date):
    try:
        start = ee.Date(target_date)
        end = start.advance(1, 'day')
        point = ee.Geometry.Point([14.4, 53.7])

        img = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(point) \
            .filterDate(start, end) \
            .mosaic()

        ndwi = img.normalizedDifference(['B3', 'B8'])
        water_mask = ndwi.gt(0.1)

        ndci = img.normalizedDifference(['B5', 'B4']).updateMask(water_mask)

        min_val = -0.1
        max_val = 0.2
        viz = {'min': min_val, 'max': max_val, 'palette': ['darkblue', 'blue', 'cyan', 'green', 'yellow', 'red']}
        map_id_dict = ndci.getMapId(viz)

        return map_id_dict['tile_fetcher'].url_format, min_val, max_val
    except Exception as e:
        raise Exception(f"Błąd GEE (Water Quality): {str(e)}")


def get_osm_data_bbox(min_lat, min_lon, max_lat, max_lon, feature_type):
    try:
        tags = {
            "Pomniki przyrody": '["denotation"="natural_monument"]',
            "Rezerwaty przyrody": '["boundary"="protected_area"]["protect_class"="4"]',
            "Użytki ekologiczne": '["boundary"="protected_area"]["protect_class"="6"]',
            "Przejścia dla zwierząt (ekodukty)": '["bridge"="ecoduct"]'
        }
        tag = tags.get(feature_type, '["denotation"="natural_monument"]')

        query = f"""
        [out:json][timeout:25];
        (
          node{tag}({min_lat},{min_lon},{max_lat},{max_lon});
          way{tag}({min_lat},{min_lon},{max_lat},{max_lon});
          relation{tag}({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """

        url = "https://overpass-api.de/api/interpreter"
        headers = {
            'User-Agent': 'RDOS-Monitoring-App/1.0',
            'Accept': 'application/json'
        }

        response = requests.post(url, data={'data': query}, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Błąd połączenia z serwerami Overpass OSM: {str(e)}")


# --- ZAKTUALIZOWANE FUNKCJE DLA GIOŚ (System Fallback - Bezpośrednio -> Proxy) ---

def fetch_with_fallback(target_url):
    """Pomocnicza funkcja, która próbuje połączyć się na kilka sposobów, omijając blokady."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }

    # 1. Próba bezpośrednia (szybka)
    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass  # Jeśli zablokują IP lub timeout, lecimy dalej w milczeniu

    # 2. Próba przez bramkę corsproxy.io (wydajniejsza niż allorigins)
    try:
        encoded_url = urllib.parse.quote(target_url, safe='')
        proxy_url = f"https://corsproxy.io/?{encoded_url}"
        response = requests.get(proxy_url, headers=headers, timeout=25)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(
            f"Serwery GIOŚ odrzuciły wszystkie próby połączenia (bezpośrednie i przez bramkę). Odczekaj chwilę. Błąd: {e}")


def get_gios_stations():
    """Pobiera listę stacji pomiarowych GIOŚ z Polski i filtruje woj. zachodniopomorskie."""
    try:
        target_url = "https://api.gios.gov.pl/pjp-api/rest/station/findAll"
        stations = fetch_with_fallback(target_url)

        zachodniopomorskie_stations = []
        for s in stations:
            if s.get('city') and s['city'].get('commune') and s['city']['commune'].get('provinceName'):
                if s['city']['commune']['provinceName'].upper() == 'ZACHODNIOPOMORSKIE':
                    zachodniopomorskie_stations.append(s)
        return zachodniopomorskie_stations
    except Exception as e:
        raise Exception(f"Błąd komunikacji ze stacjami GIOŚ: {e}")


def get_gios_aqi(station_id):
    """Odpytuje konkretną stację o aktualny Indeks Jakości Powietrza."""
    try:
        target_url = f"https://api.gios.gov.pl/pjp-api/rest/aqindex/getIndex/{station_id}"
        data = fetch_with_fallback(target_url)

        if data.get('stIndexLevel') and data['stIndexLevel'].get('indexLevelName'):
            return data['stIndexLevel']['indexLevelName'], data.get('stCalcDate', 'Brak daty')
        else:
            return "Brak danych pomiarowych", "Brak daty"
    except Exception:
        return "Błąd odczytu", "Brak daty"