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

        # MAGIA JEST TUTAJ: Zamiast całego województwa, używamy jednego punktu
        # To zapytanie jest 100x szybsze i gwarantuje znalezienie dat przelotu!
        point = ee.Geometry.Point([15.6, 53.6])

        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(str(start_date), str(end_date)) \
            .filterBounds(point)

        # Pobieramy daty z metadanych
        times = s5p.aggregate_array('system:time_start').getInfo()

        if not times:
            return []

        # Zamieniamy je na ładną listę (bez duplikatów)
        dates = pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
        dates.sort(reverse=True)
        return dates

    except Exception as e:
        raise Exception(f"Błąd GEE: {str(e)}")


def get_atmospheric_layer(target_date, parameter):
    try:
        start = ee.Date(target_date)
        end = start.advance(1, 'day')

        # Obniżone progi - zachodniopomorskie jest czyste, więc musimy być bardziej czuli!
        if parameter == "NO2 (Dwutlenek azotu)":
            col, band, threshold, max_val = 'L3_NO2', 'tropospheric_NO2_column_number_density', 0.00002, 0.0001
        elif parameter == "SO2 (Dwutlenek siarki)":
            col, band, threshold, max_val = 'L3_SO2', 'SO2_column_number_density', 0.00001, 0.0005
        elif parameter == "CO (Tlenek węgla)":
            col, band, threshold, max_val = 'L3_CO', 'CO_column_number_density', 0.02, 0.05
        elif parameter == "Aerozole (Smog / Pyły)":
            col, band, threshold, max_val = 'L3_AER_AI', 'absorbing_aerosol_index', 0.1, 2.0
        else:
            return None

        # Pobieramy obraz (bez ciężkiego wycinania wielokątem)
        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(start, end) \
            .select(band) \
            .mean()

        # Odcinamy tylko całkowicie puste/najczystsze tło
        s5p_high = s5p.updateMask(s5p.gt(threshold))

        viz = {'min': threshold, 'max': max_val, 'palette': ['yellow', 'orange', 'red', 'purple']}
        map_id_dict = s5p_high.getMapId(viz)

        return map_id_dict['tile_fetcher'].url_format
    except Exception as e:
        # Zwracamy prawdziwy błąd, a nie None
        raise Exception(f"Błąd GEE: {str(e)}")