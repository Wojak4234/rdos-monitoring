# gee_ops.py

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
        mapping = {"NO2 (Dwutlenek azotu)": 'L3_NO2', "SO2 (Dwutlenek siarki)": 'L3_SO2', "CO (Tlenek węgla)": 'L3_CO',
                   "Aerozole (Smog / Pyły)": 'L3_AER_AI'}
        col = mapping.get(parameter)
        point = ee.Geometry.Point([15.6, 53.6])
        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}').filterDate(
            datetime.date.today() - datetime.timedelta(days=days_back), datetime.date.today()).filterBounds(point)
        times = s5p.aggregate_array('system:time_start').getInfo()
        return pd.to_datetime(times, unit='ms').strftime('%Y-%m-%d').unique().tolist()
    except:
        return []


def get_atmospheric_layer(target_date, parameter):
    try:
        start = ee.Date(target_date)
        configs = {
            "NO2 (Dwutlenek azotu)": ('L3_NO2', 'tropospheric_NO2_column_number_density', 0.00002, 0.0001),
            "SO2 (Dwutlenek siarki)": ('L3_SO2', 'SO2_column_number_density', 0.00001, 0.0005),
            "CO (Tlenek węgla)": ('L3_CO', 'CO_column_number_density', 0.02, 0.05),
            "Aerozole (Smog / Pyły)": ('L3_AER_AI', 'absorbing_aerosol_index', 0.1, 2.0)
        }
        col, band, threshold, max_val = configs[parameter]
        s5p = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}').filterDate(start, start.advance(1, 'day')).select(
            band).mean()
        viz = {'min': threshold, 'max': max_val, 'palette': ['yellow', 'orange', 'red', 'purple']}
        return s5p.updateMask(s5p.gt(threshold)).getMapId(viz)['tile_fetcher'].url_format, threshold, max_val
    except:
        return None, None, None


def get_s2_water_dates(days_back=90):
    try:
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(ee.Geometry.Point([14.4, 53.7])).filterDate(
            datetime.date.today() - datetime.timedelta(days=days_back), datetime.date.today()).filter(
            ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))
        return pd.to_datetime(s2.aggregate_array('system:time_start').getInfo(), unit='ms').strftime(
            '%Y-%m-%d').unique().tolist()
    except:
        return []


def get_water_quality_layer(target_date):
    try:
        start = ee.Date(target_date)
        img = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(
            ee.Geometry.Point([14.4, 53.7])).filterDate(start, start.advance(1, 'day')).mosaic()
        ndci = img.normalizedDifference(['B5', 'B4']).updateMask(img.normalizedDifference(['B3', 'B8']).gt(0.1))
        return \
        ndci.getMapId({'min': -0.1, 'max': 0.2, 'palette': ['darkblue', 'blue', 'cyan', 'green', 'yellow', 'red']})[
            'tile_fetcher'].url_format, -0.1, 0.2
    except:
        return None, None, None