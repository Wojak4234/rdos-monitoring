import ee
import pandas as pd


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
                layer = img.normalizedDifference(['B3', 'B8']).rename('INDEX')  # Zielony i NIR
            elif index_type == "NDMI (Wilgotność roślin)":
                layer = img.normalizedDifference(['B8', 'B11']).rename('INDEX')  # NIR i SWIR1
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
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
        return df[['Wartość']]

    except Exception as e:
        print(f"Błąd szeregu czasowego wskaźnika: {e}")
        return None


def get_atmospheric_no2_data(start_date, end_date):
    """Pobiera dane stężenia NO2 z Sentinel-5P dla obszaru Polski / regionu"""
    try:
        # Zbiór Sentinel-5P Tropospheric NO2
        s5p = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2') \
            .filterDate(str(start_date), str(end_date)) \
            .select('tropospheric_NO2_column_number_density') \
            .mean()  # Średnia z wybranego okresu

        return s5p
    except Exception as e:
        print(f"Błąd pobierania danych S5P: {e}")
        return None