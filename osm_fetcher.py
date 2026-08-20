# osm_fetcher.py

import requests


def get_osm_data_bbox(min_lat, min_lon, max_lat, max_lon, feature_type):
    """
    Pobiera dane wektorowe z OpenStreetMap na podstawie zadanego bounding boxa i typu obiektu.
    """
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

    try:
        response = requests.post(url, data={'data': query}, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Błąd połączenia z serwerami OpenStreetMap (Overpass API): {e}")