import requests
import pandas as pd
import datetime

# Rozszerzona, stała lista stacji dla Zachodniopomorskiego (zamiast powolnego wyszukiwania w GIOŚ)
STACJE_ZACHODNIOPOMORSKIE = [
    {"id": 1, "stationName": "Szczecin - Piłsudskiego", "gegrLat": 53.432, "gegrLon": 14.553},
    {"id": 2, "stationName": "Szczecin - Andrzejewskiego", "gegrLat": 53.383, "gegrLon": 14.633},
    {"id": 3, "stationName": "Szczecin - Łączna", "gegrLat": 53.468, "gegrLon": 14.577},
    {"id": 4, "stationName": "Koszalin - Armii Krajowej", "gegrLat": 54.193, "gegrLon": 16.176},
    {"id": 5, "stationName": "Szczecinek - Przemysłowa", "gegrLat": 53.712, "gegrLon": 16.697},
    {"id": 6, "stationName": "Wałcz - Chrząstkowo", "gegrLat": 53.280, "gegrLon": 16.452},
    {"id": 7, "stationName": "Widuchowa - Bulwar", "gegrLat": 53.125, "gegrLon": 14.385},
    {"id": 8, "stationName": "Świnoujście - Mickiewicza", "gegrLat": 53.911, "gegrLon": 14.250},
    {"id": 9, "stationName": "Police - Piaskowa", "gegrLat": 53.553, "gegrLon": 14.580},
    {"id": 10, "stationName": "Stargard - Bogusława IV", "gegrLat": 53.336, "gegrLon": 15.042},
    {"id": 11, "stationName": "Kołobrzeg - Złota", "gegrLat": 54.175, "gegrLon": 15.586},
    {"id": 12, "stationName": "Białogard - Kopernika", "gegrLat": 54.004, "gegrLon": 15.989},
    {"id": 13, "stationName": "Goleniów - Niepodległości", "gegrLat": 53.561, "gegrLon": 14.827},
    {"id": 14, "stationName": "Gryfino - Chrobrego", "gegrLat": 53.252, "gegrLon": 14.488},
    {"id": 15, "stationName": "Będargowo (Stacja Wirtualna)", "gegrLat": 53.385, "gegrLon": 14.441},
]


def get_gios_stations():
    """
    Zwraca natychmiast listę predefiniowanych stacji,
    z pominięciem awaryjnego API GIOŚ.
    """
    return STACJE_ZACHODNIOPOMORSKIE


def get_gios_aqi(station_id, lat, lon):
    """
    Pobiera aktualny stan powietrza z superszybkiego API Open-Meteo (Copernicus)
    i oblicza Polski Indeks Jakości Powietrza.
    """
    try:
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=pm10,pm2_5,nitrogen_dioxide&timezone=Europe%2FWarsaw"
        resp = requests.get(url, timeout=5)
        data = resp.json()

        curr = data.get("current", {})
        pm10 = curr.get("pm10", 0)
        pm25 = curr.get("pm2_5", 0)
        no2 = curr.get("nitrogen_dioxide", 0)
        time_str = curr.get("time", "Brak danych").replace("T", " ")

        # Algorytm przypisujący polskie etykiety (Indeks GIOŚ) na podstawie europejskich danych
        if pm10 > 150 or pm25 > 110 or no2 > 400: return "Bardzo zły", time_str
        if pm10 > 110 or pm25 > 75 or no2 > 200: return "Zły", time_str
        if pm10 > 80 or pm25 > 55 or no2 > 150: return "Dostateczny", time_str
        if pm10 > 50 or pm25 > 35 or no2 > 100: return "Umiarkowany", time_str
        if pm10 > 20 or pm25 > 13 or no2 > 40: return "Dobry", time_str
        return "Bardzo dobry", time_str

    except Exception:
        return "Brak danych", str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))


def get_historical_air_quality(lat, lon, past_days=3):
    """
    Pobiera pełne dane historyczne (co godzinę) bezpośrednio z europejskich modeli.
    """
    try:
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,nitrogen_dioxide,sulphur_dioxide,ozone,carbon_monoxide&past_days={past_days}&timezone=Europe%2FWarsaw"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        # Tworzymy DataFrame z nazwami kolumn idealnie pasującymi do Twojego app.py
        df = pd.DataFrame({
            "Czas": pd.to_datetime(times),
            "PM10 (µg/m³)": hourly.get("pm10", []),
            "PM2.5 (µg/m³)": hourly.get("pm2_5", []),
            "NO2 (µg/m³)": hourly.get("nitrogen_dioxide", []),
            "SO2 (µg/m³)": hourly.get("sulphur_dioxide", []),
            "O3 (µg/m³)": hourly.get("ozone", []),
            "CO (µg/m³)": hourly.get("carbon_monoxide", [])
        })

        df.set_index("Czas", inplace=True)
        # Usunięcie wierszy z całkowitym brakiem danych
        df.dropna(how='all', inplace=True)

        return df
    except Exception as e:
        return pd.DataFrame()