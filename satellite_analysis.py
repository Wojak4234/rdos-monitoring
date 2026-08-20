import ee
import pandas as pd
import datetime


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


def get_available_dates(parameter, days_back=60):
    """Przeszukuje bazę GEE i zwraca listę dostępnych dat dla wybranego gazu z ostatnich X dni"""
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

        # Liczymy daty: od dzisiaj do 'days_back' dni wstecz
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        region = ee.FeatureCollection("FAO/GAUL/2015/level1") \
            .filter(ee.Filter.eq('ADM1_NAME', 'Zachodniopomorskie'))

        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(str(start_date), str(end_date)) \
            .filterBounds(region)

        # Funkcja wydobywająca daty z metadanych zdjęć
        def get_date(image):
            return ee.Feature(None, {'date': image.date().format('YYYY-MM-dd')})

        # Zbieramy dane do lokalnego Pythona i wyciągamy unikalne daty
        dates_info = s5p.map(get_date).getInfo()
        valid_dates = set()
        for feat in dates_info.get('features', []):
            valid_dates.add(feat['properties']['date'])

        # Zwracamy posortowaną listę (od najnowszych do najstarszych)
        return sorted(list(valid_dates), reverse=True)
    except Exception as e:
        print(f"Błąd wyszukiwania dat: {e}")
        return []


def get_atmospheric_layer(target_date, parameter):
    try:
        region = ee.FeatureCollection("FAO/GAUL/2015/level1") \
            .filter(ee.Filter.eq('ADM1_NAME', 'Zachodniopomorskie'))

        start = ee.Date(target_date)
        end = start.advance(1, 'day')

        if parameter == "NO2 (Dwutlenek azotu)":
            col, band, threshold, max_val = 'L3_NO2', 'tropospheric_NO2_column_number_density', 0.00004, 0.00015
        elif parameter == "SO2 (Dwutlenek siarki)":
            col, band, threshold, max_val = 'L3_SO2', 'SO2_column_number_density', 0.0001, 0.0005
        elif parameter == "CO (Tlenek węgla)":
            col, band, threshold, max_val = 'L3_CO', 'CO_column_number_density', 0.03, 0.05
        elif parameter == "Aerozole (Smog / Pyły)":
            col, band, threshold, max_val = 'L3_AER_AI', 'absorbing_aerosol_index', 0.5, 2.0
        else:
            return None

        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(start, end) \
            .filterBounds(region) \
            .select(band) \
            .mean() \
            .clip(region)

        s5p_high = s5p.updateMask(s5p.gt(threshold))

        viz = {'min': threshold, 'max': max_val, 'palette': ['yellow', 'orange', 'red', 'purple']}
        map_id_dict = s5p_high.getMapId(viz)

        return map_id_dict['tile_fetcher'].url_format
    except Exception as e:
        print(f"Błąd pobierania warstwy S5P: {e}")
        return None