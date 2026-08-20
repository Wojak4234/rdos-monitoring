# data_fetchers.py

import requests
import urllib.parse
import json
import pandas as pd


def get_osm_data_bbox(min_lat, min_lon, max_lat, max_lon, feature_type):
    """Pobiera wektory z OpenStreetMap na podstawie okna Bounding Box."""
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
    headers = {'User-Agent': 'RDOS-Monitoring-App/1.0', 'Accept': 'application/json'}
    response = requests.post(url, data={'data': query}, headers=headers)
    response.raise_for_status()
    return response.json()


def fetch_with_fallback(target_url):
    """Próbuje połączyć się z GIOŚ z wydłużonym czasem i różnymi metodami."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 1. Próba bezpośrednia
    try:
        r = requests.get(target_url, headers=headers, timeout=5)
        if r.status_code == 200: return r.json()
    except:
        pass

    # 2. Próba przez bramkę Codetabs
    try:
        r = requests.get(f"https://api.codetabs.com/v1/proxy?quest={target_url}", timeout=10)
        if r.status_code == 200: return r.json()
    except:
        pass

    # 3. Ostateczność: Allorigins w trybie JSON wrap
    try:
        encoded_url = urllib.parse.quote(target_url, safe='')
        r = requests.get(f"https://api.allorigins.win/get?url={encoded_url}", timeout=10)
        if r.status_code == 200: return json.loads(r.json()['contents'])
    except Exception as e:
        raise Exception(f"GIOŚ zablokował połączenie (403/410). Błąd: {e}")

    raise Exception("GIOŚ zablokował połączenie.")


def get_gios_stations():
    """Pobiera listę stacji pomiarowych GIOŚ."""
    try:
        target_url = "https://api.gios.gov.pl/pjp-api/rest/station/findAll"
        stations = fetch_with_fallback(target_url)
        return [s for s in stations if
                s.get('city') and s['city'].get('commune') and s['city']['commune'].get('provinceName',
                                                                                        '').upper() == 'ZACHODNIOPOMORSKIE']
    except:
        # Baza awaryjna
        return [
            {"id": 730, "stationName": "Szczecin, ul. Andrzejewskiego", "gegrLat": "53.4321", "gegrLon": "14.5828"},
            {"id": 732, "stationName": "Szczecin, ul. Piłsudskiego", "gegrLat": "53.4325", "gegrLon": "14.5483"},
            {"id": 724, "stationName": "Koszalin, ul. Armii Krajowej", "gegrLat": "54.1937", "gegrLon": "16.1773"},
            {"id": 735, "stationName": "Szczecinek, ul. Przemysłowa", "gegrLat": "53.7033", "gegrLon": "16.7175"},
            {"id": 738, "stationName": "Widuchowa, ul. Bulwar Rybacki", "gegrLat": "53.1237", "gegrLon": "14.3897"}
        ]


def get_gios_aqi(station_id, lat=None, lon=None):
    """Odpytuje konkretną stację. Fallback do Copernicus/Open-Meteo w razie awarii GIOŚ."""
    try:
        target_url = f"https://api.gios.gov.pl/pjp-api/rest/aqindex/getIndex/{station_id}"
        data = fetch_with_fallback(target_url)
        if data and data.get('stIndexLevel') and data['stIndexLevel'].get('indexLevelName'):
            return data['stIndexLevel']['indexLevelName'], data.get('stCalcDate', 'Brak daty')
        raise Exception("Brak danych GIOŚ")
    except:
        if lat and lon:
            try:
                om_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi"
                r = requests.get(om_url, timeout=5)
                if r.status_code == 200:
                    aqi = r.json()['current']['european_aqi']
                    time_str = r.json()['current']['time']
                    if aqi <= 20:
                        return "Bardzo dobry (Zapas: Copernicus)", time_str
                    elif aqi <= 40:
                        return "Dobry (Zapas: Copernicus)", time_str
                    elif aqi <= 60:
                        return "Umiarkowany (Zapas: Copernicus)", time_str
                    elif aqi <= 80:
                        return "Dostateczny (Zapas: Copernicus)", time_str
                    elif aqi <= 100:
                        return "Zły (Zapas: Copernicus)", time_str
                    else:
                        return "Bardzo zły (Zapas: Copernicus)", time_str
            except:
                pass
        return "Brak danych z serwerów", "Brak daty"


def get_historical_air_quality(lat, lon, past_days=3):
    """Pobiera historyczne dane (PM10, PM2.5, NO2, Ozon) z modelu atmosferycznego."""
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,nitrogen_dioxide,ozone&past_days={past_days}"
    r = requests.get(url, timeout=10)
    if r.status_code == 200:
        data = r.json()['hourly']
        df = pd.DataFrame(data)
        df.rename(columns={'pm10': 'PM10 (µg/m³)', 'pm2_5': 'PM2.5 (µg/m³)', 'nitrogen_dioxide': 'NO2 (µg/m³)',
                           'ozone': 'Ozon (µg/m³)'}, inplace=True)
        return df
    return None