import ee
import pandas as pd


def calculate_ndvi_time_series(geojson_feature, start_date, end_date):
    try:
        roi = ee.Geometry(geojson_feature['geometry'])

        # Używamy oficjalnego, zharmonizowanego zbioru zaleconego przez Google
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(roi) \
            .filterDate(str(start_date), str(end_date)) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25))

        def process_image(img):
            ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
            date_str = img.date().format('YYYY-MM-dd')
            mean_dict = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=30,
                maxPixels=1e8
            )
            return ee.Feature(None, {'date': date_str, 'NDVI': mean_dict.get('NDVI')})

        ts_collection = s2.map(process_image)
        info = ts_collection.getInfo()

        data = []
        for feat in info.get('features', []):
            props = feat['properties']
            d = props.get('date')
            val = props.get('NDVI')
            if d and val is not None:
                data.append({'date': d, 'NDVI': val})

        if not data:
            return None

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
        return df

    except Exception as e:
        print(f"Błąd szeregu czasowego: {e}")
        return None