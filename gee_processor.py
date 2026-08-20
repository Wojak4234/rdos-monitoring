# gee_processor.py

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

            mean_dict = layer.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e8)
            return ee.Feature(None, {'date': img.date().format('YYYY-MM-dd'), 'VAL': mean_dict.get('INDEX')})

        info = s2.map(process_image).getInfo()
        data = [{'date': feat['properties']['date'], 'Wartość': feat['properties']['VAL']} for feat in
                info.get('features', []) if feat['properties']['VAL'] is not None]

        if not data: return None
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date').set_index('date')[['Wartość']]
    except Exception as e:
        print(f"Błąd szeregu czasowego: {e}")
        return None


def get_available_dates(parameter, days_back=90):
    try:
        mapping = {
            "NO2 (Dwutlenek azotu)": 'L3_NO2',
            "SO2 (Dwutlenek siarki)": 'L3_SO2',
            "CO (Tlenek węgla)": 'L3_CO',
            "Aerozole (Smog / Pyły)": 'L3_AER_AI'
        }
        col = mapping.get(parameter)
        if not col: return []
        point = ee.Geometry.Point([15.6, 53.6])

        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        # NAPRAWA: Użycie ee.Date() zamiast surowych stringów
        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}') \
            .filterDate(ee.Date(str(start_date)), ee.Date(str(end_date))) \
            .filterBounds(point)

        times = s5p.aggregate_array('system:time_start').getInfo()
        if not times: return []
        dates = pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
        dates.sort(reverse=True)
        return dates
    except Exception as e:
        raise Exception(f"Błąd GEE: {e}")


def get_atmospheric_layer(target_date, parameter):
    try:
        start = ee.Date(target_date)
        end = start.advance(1, 'day')
        configs = {
            "NO2 (Dwutlenek azotu)": ('L3_NO2', 'tropospheric_NO2_column_number_density', 0.00002, 0.0001),
            "SO2 (Dwutlenek siarki)": ('L3_SO2', 'SO2_column_number_density', 0.00001, 0.0005),
            "CO (Tlenek węgla)": ('L3_CO', 'CO_column_number_density', 0.02, 0.05),
            "Aerozole (Smog / Pyły)": ('L3_AER_AI', 'absorbing_aerosol_index', 0.1, 2.0)
        }
        col, band, threshold, max_val = configs[parameter]
        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}').filterDate(start, end).select(band).mean()
        s5p_high = s5p.updateMask(s5p.gt(threshold))
        viz = {'min': threshold, 'max': max_val, 'palette': ['yellow', 'orange', 'red', 'purple']}
        return s5p_high.getMapId(viz)['tile_fetcher'].url_format, threshold, max_val
    except Exception as e:
        raise Exception(f"Błąd GEE: {e}")


def get_s2_water_dates(days_back=90):
    try:
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)
        point = ee.Geometry.Point([14.4, 53.7])

        # Poprawka również tutaj dla spójności
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(point) \
            .filterDate(ee.Date(str(start_date)), ee.Date(str(end_date))) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))

        times = s2.aggregate_array('system:time_start').getInfo()
        if not times: return []
        dates = pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
        dates.sort(reverse=True)
        return dates
    except Exception as e:
        raise Exception(f"Błąd GEE (S2 Water Dates): {e}")


def get_water_quality_layer(target_date):
    try:
        start = ee.Date(target_date)
        end = start.advance(1, 'day')
        point = ee.Geometry.Point([14.4, 53.7])
        img = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(point).filterDate(start, end).mosaic()
        ndwi = img.normalizedDifference(['B3', 'B8'])
        water_mask = ndwi.gt(0.1)
        ndci = img.normalizedDifference(['B5', 'B4']).updateMask(water_mask)
        min_val = -0.1
        max_val = 0.2
        viz = {'min': min_val, 'max': max_val, 'palette': ['darkblue', 'blue', 'cyan', 'green', 'yellow', 'red']}
        return ndci.getMapId(viz)['tile_fetcher'].url_format, min_val, max_val
    except Exception as e:
        raise Exception(f"Błąd GEE (Water Quality): {e}")