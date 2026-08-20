# gios_fetcher.py

import requests
import urllib.parse
import json
import pandas as pd


def fetch_with_fallback(target_url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        r = requests.get(target_url, headers=headers, timeout=5)
        if r.status_code == 200: return r.json()
    except:
        pass

    try:
        r = requests.get(f"https://api.codetabs.com/v1/proxy?quest={target_url}", timeout=10)
        if r.status_code == 200: return r.json()
    except:
        pass

    try:
        encoded_url = urllib.parse.quote(target_url, safe='')
        r = requests.get(f"https://api.allorigins.win/get?url={encoded_url}", timeout=10)
        if r.status_code == 200: return json.loads(r.json()['contents'])
    except Exception as e:
        raise Exception(f"GIOŚ zablokował połączenie (403/410). Błąd: {e}")

    raise Exception("GIOŚ zablokował połączenie.")


def get_gios_stations():
    try:
        target_url = "https://api.gios.gov.pl/pjp-api/rest/station/findAll"
        stations = fetch_with_fallback(target_url)
        return [s for s in stations if
                s.get('city') and s['city'].get('commune') and s['city']['commune'].get('provinceName',
                                                                                        '').upper() == 'ZACHODNIOPOMORSKIE']
    except:
        return [
            {"id": 730, "stationName": "Szczecin, ul. Andrzejewskiego", "gegrLat": "53.4321", "gegrLon": "14.5828"},
            {"id": 732, "stationName": "Szczecin, ul. Piłsudskiego", "gegrLat": "53.4325", "gegrLon": "14.5483"},
            {"id": 724, "stationName": "Koszalin, ul. Armii Krajowej", "gegrLat": "54.1937", "gegrLon": "16.1773"},
            {"id": 735, "stationName": "Szczecinek, ul. Przemysłowa", "gegrLat": "53.7033", "gegrLon": "16.7175"},
            {"id": 738, "stationName": "Widuchowa, ul. Bulwar Rybacki", "gegrLat": "53.1237", "gegrLon": "14.3897"}
        ]


def get_gios_aqi(station_id, lat=None, lon=None):
    try:
        data = fetch_with_fallback(f"https://api.gios.gov.pl/pjp-api/rest/aqindex/getIndex/{station_id}")
        if data and data.get('stIndexLevel') and data['stIndexLevel'].get('indexLevelName'):
            return data['stIndexLevel']['indexLevelName'], data.get('stCalcDate', 'Brak daty')
        raise Exception("Brak danych GIOŚ")
    except:
        if lat and lon:
            try:
                r = requests.get(
                    f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi",
                    timeout=5)
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
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,nitrogen_dioxide,ozone&past_days={past_days}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            df = pd.DataFrame(r.json()['hourly'])
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
            df.rename(columns={
                'pm10': 'PM10 (µg/m³)',
                'pm2_5': 'PM2.5 (µg/m³)',
                'nitrogen_dioxide': 'NO2 (µg/m³)',
                'ozone': 'Ozon (µg/m³)'
            }, inplace=True)
            return df.dropna()
    except:
        pass
    return None