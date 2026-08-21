# inspector.py

import ee
import datetime
from shapely.geometry import shape


def run_regional_inspection(n2000_features=None):
    alerts = []
    warnings = []
    ok_status = []
    map_data = []  # Tutaj będziemy zbierać koordynaty do wyrysowania na mapie!

    end_date = ee.Date(datetime.date.today().isoformat())
    region_zach = ee.Geometry.Rectangle([14.0, 52.6, 17.0, 54.6])

    # ---------------------------------------------------------
    # 1. POWIETRZE (S5P)
    # ---------------------------------------------------------
    start_air = end_date.advance(-3, 'day')
    air_configs = {
        "NO2 (Dwutlenek azotu)": ('L3_NO2', 'tropospheric_NO2_column_number_density', 0.0001, 0.00007),
        "SO2 (Dwutlenek siarki)": ('L3_SO2', 'SO2_column_number_density', 0.0005, 0.0003),
        "CO (Tlenek węgla)": ('L3_CO', 'CO_column_number_density', 0.04, 0.035)
    }

    for name, (col, band, thr_alert, thr_warn) in air_configs.items():
        try:
            img = ee.ImageCollection(f'COPERNICUS/S5P/OFFL/{col}').filterDate(start_air, end_date).select(band).max()
            val = img.reduceRegion(reducer=ee.Reducer.max(), geometry=region_zach, scale=5000, bestEffort=True).get(
                band).getInfo()

            if val and val >= thr_warn:
                # Elastyczny próg (95% z maxa), aby zniwelować błędy precyzji zmiennoprzecinkowej w GEE
                mask = img.gte(ee.Number(val).multiply(0.95))
                coords = ee.Image.pixelLonLat().updateMask(mask).reduceRegion(reducer=ee.Reducer.first(),
                                                                              geometry=region_zach,
                                                                              scale=5000).getInfo()
                lat, lon = coords.get('latitude'), coords.get('longitude')

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat and lon else "Brak geolokalizacji"

                if lat and lon:
                    map_data.append(
                        {'type': 'air', 'lat': lat, 'lon': lon, 'popup': f"Anomalia {name.split()[0]}: {val:.5f}",
                         'color': 'purple'})

                if val >= thr_alert:
                    alerts.append(
                        f"**{name}:** Krytyczne stężenie! Zarejestrowane maksimum: **{val:.5f} mol/m²**. Epicentrum: {loc_str}")
                else:
                    warnings.append(f"**{name}:** Podwyższone stężenie (Max: {val:.5f} mol/m²). Epicentrum: {loc_str}")
            elif val:
                ok_status.append(f"**{name}:** W normie (Max: {val:.5f}).")
        except Exception as e:
            pass

    # ---------------------------------------------------------
    # 2. JAKOŚĆ WÓD (NDCI)
    # ---------------------------------------------------------
    try:
        start_water = end_date.advance(-10, 'day')
        s2_water = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(region_zach).filterDate(start_water, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))

        if s2_water.size().getInfo() > 0:
            img = s2_water.mosaic()
            ndwi = img.normalizedDifference(['B3', 'B8'])
            water_mask = ndwi.gt(0.1)
            ndci = img.normalizedDifference(['B5', 'B4']).updateMask(water_mask)

            max_ndci = ndci.reduceRegion(reducer=ee.Reducer.max(), geometry=region_zach, scale=100,
                                         bestEffort=True).get('nd').getInfo()

            if max_ndci and max_ndci > 0.05:
                mask = ndci.gte(ee.Number(max_ndci).subtract(0.01))
                coords = ee.Image.pixelLonLat().updateMask(mask).reduceRegion(reducer=ee.Reducer.first(),
                                                                              geometry=region_zach, scale=100).getInfo()
                lat, lon = coords.get('latitude'), coords.get('longitude')

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat and lon else ""
                if lat and lon:
                    map_data.append({'type': 'water', 'lat': lat, 'lon': lon, 'popup': f"Zakwit NDCI: {max_ndci:.3f}",
                                     'color': 'darkblue'})

                if max_ndci > 0.12:
                    alerts.append(
                        f"**Wody powierzchniowe (Chlorofil-a):** Ekstremalnie wysoki NDCI (**{max_ndci:.3f}**). Ryzyko masowego zakwitu toksycznych glonów (np. złotej algi). {loc_str}")
                else:
                    warnings.append(
                        f"**Wody powierzchniowe:** Podwyższony chlorofil-a (NDCI: {max_ndci:.3f}). {loc_str}")
            elif max_ndci:
                ok_status.append(f"**Jakość wód (NDCI):** Stabilna, brak sygnatur zakwitów (Max NDCI: {max_ndci:.3f}).")
    except Exception as e:
        pass

    # ---------------------------------------------------------
    # 3. WILGOTNOŚĆ (NDMI) i N2000
    # ---------------------------------------------------------
    try:
        if n2000_features:
            points = []
            features_dict = {}
            for f in n2000_features:
                name = f['properties'].get('nazwa', f['properties'].get('SITE_NAME', 'Nieznany Obszar'))
                c = shape(f['geometry']).centroid
                points.append(ee.Feature(ee.Geometry.Point([c.x, c.y]), {'name': name}))
                features_dict[name] = (c.y, c.x)

            fc = ee.FeatureCollection(points)

            def add_buffer(feat):
                return feat.buffer(1000)

            fc_buf = fc.map(add_buffer)

            mid_date = end_date.advance(-15, 'day')
            start_moisture = mid_date.advance(-15, 'day')
            s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region_zach)

            recent_ndmi = s2.filterDate(mid_date, end_date).median().normalizedDifference(['B8', 'B11'])
            past_ndmi = s2.filterDate(start_moisture, mid_date).median().normalizedDifference(['B8', 'B11'])
            diff = recent_ndmi.subtract(past_ndmi)
            results = diff.reduceRegions(collection=fc_buf, reducer=ee.Reducer.mean(), scale=100).getInfo()

            anomalies_dict = {}
            for feat in results.get('features', []):
                d = feat['properties'].get('mean')
                n = feat['properties'].get('name')
                if d is not None and d < -0.05:
                    if n not in anomalies_dict or d < anomalies_dict[n]:
                        anomalies_dict[n] = d

            anomalies = list(anomalies_dict.items())
            if anomalies:
                anomalies.sort(key=lambda x: x[1])
                worst_name, worst_val = anomalies[0]

                # Dodaj epicentrum suszy do mapy
                lat_c, lon_c = features_dict.get(worst_name, (None, None))
                if lat_c and lon_c:
                    map_data.append({'type': 'drought', 'lat': lat_c, 'lon': lon_c,
                                     'popup': f"Susza: {worst_name} (Δ{worst_val:.2f})", 'color': 'orange'})

                if worst_val < -0.15:
                    alerts.append(
                        f"**Błyskawiczna Susza (Natura 2000):** Obszar **{worst_name}** wykazuje drastyczny spadek wilgotności (Δ {worst_val:.3f}).")
                elif worst_val < -0.10:
                    warnings.append(
                        f"**Przesuszenie (Natura 2000):** Obszar **{worst_name}** wykazuje znaczący spadek wilgotności (Δ {worst_val:.3f}).")

                if len(anomalies) > 1:
                    other_sites = ", ".join([f"{x[0]} (Δ{x[1]:.2f})" for x in anomalies[1:4]])
                    warnings.append(f"**Kolejne przesuszone obszary N2000:** {other_sites}")
            else:
                ok_status.append("**Obszary Natura 2000:** Stabilna wilgotność w skali regionu.")
    except Exception as e:
        pass

    return alerts, warnings, ok_status, map_data