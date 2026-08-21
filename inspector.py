# inspector.py

import ee
import datetime
from shapely.geometry import shape


def run_regional_inspection(n2000_features=None):
    """
    Wykonuje skanowanie z poprawioną geolokalizacją,
    filtrowaniem duplikatów N2000 oraz formatowaniem PDF (<b>).
    """
    alerts = []
    warnings = []
    ok_status = []

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
                # Rozwiązanie problemu "Brak dokładnych danych": szukamy pikseli w granicach 99% wartości maksymalnej
                mask = img.gte(ee.Number(val).multiply(0.99))
                coords = ee.Image.pixelLonLat().updateMask(mask).reduceRegion(reducer=ee.Reducer.first(),
                                                                              geometry=region_zach,
                                                                              scale=5000).getInfo()
                lat, lon = coords.get('latitude'), coords.get('longitude')

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat else "Brak dokładnych danych geolokalizacyjnych"

                if val >= thr_alert:
                    alerts.append(
                        f"<b>{name}:</b> Krytyczne stężenie! Zarejestrowane maksimum: <b>{val:.5f} mol/m²</b>. Lokalizacja epicentrum zanieczyszczeń: {loc_str}")
                else:
                    warnings.append(
                        f"<b>{name}:</b> Podwyższone stężenie (Maksimum: {val:.5f} mol/m²). Lokalizacja: {loc_str}")
            elif val:
                ok_status.append(f"<b>{name}:</b> W normie (Max: {val:.5f}).")
        except Exception as e:
            print(f"Błąd S5P: {e}")

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

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat else ""

                if max_ndci > 0.12:
                    alerts.append(
                        f"<b>Wody powierzchniowe (Chlorofil-a):</b> Ekstremalnie wysoki wskaźnik NDCI (<b>{max_ndci:.3f}</b>). Bardzo wysokie ryzyko masowego zakwitu toksycznych glonów (np. złotej algi). Wskazana pilna inspekcja w miejscu: {loc_str}")
                else:
                    warnings.append(
                        f"<b>Wody powierzchniowe:</b> Podwyższony chlorofil-a (NDCI: {max_ndci:.3f}). Zwiększona masa materii organicznej. {loc_str}")
            elif max_ndci:
                ok_status.append(
                    f"<b>Jakość wód (NDCI):</b> Stabilna, brak sygnatur rozległych zakwitów (Max NDCI w regionie: {max_ndci:.3f}).")
    except Exception as e:
        print(f"Błąd Wody: {e}")

    # ---------------------------------------------------------
    # 3. WILGOTNOŚĆ (NDMI) i N2000
    # ---------------------------------------------------------
    try:
        if n2000_features:
            points = []
            for f in n2000_features:
                name = f['properties'].get('nazwa', f['properties'].get('SITE_NAME', 'Nieznany Obszar'))
                c = shape(f['geometry']).centroid
                points.append(ee.Feature(ee.Geometry.Point([c.x, c.y]), {'name': name}))

            fc = ee.FeatureCollection(points)

            def add_buffer(feat):
                return feat.buffer(1000)

            fc_buf = fc.map(add_buffer)

            mid_date = end_date.advance(-15, 'day')
            start_moisture = mid_date.advance(-15, 'day')
            s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region_zach)

            recent_ndmi = s2.filterDate(mid_date, end_date).median().normalizedDifference(['B8', 'B11']).rename('NDMI')
            past_ndmi = s2.filterDate(start_moisture, mid_date).median().normalizedDifference(['B8', 'B11']).rename(
                'NDMI')

            diff = recent_ndmi.subtract(past_ndmi)
            results = diff.reduceRegions(collection=fc_buf, reducer=ee.Reducer.mean(), scale=100).getInfo()

            # SŁOWNIK: Filtruje wielokrotne poligony tego samego obszaru N2000
            anomalies_dict = {}
            for feat in results.get('features', []):
                d = feat['properties'].get('mean')
                n = feat['properties'].get('name')
                if d is not None and d < -0.05:
                    if n not in anomalies_dict or d < anomalies_dict[n]:  # Zapisuje tylko największy spadek
                        anomalies_dict[n] = d

            anomalies = list(anomalies_dict.items())

            if anomalies:
                anomalies.sort(key=lambda x: x[1])
                worst_name, worst_val = anomalies[0]

                if worst_val < -0.15:
                    alerts.append(
                        f"<b>Błyskawiczna Susza (Natura 2000):</b> Obszar <b>{worst_name}</b> odnotował drastyczny spadek wilgotności (spadek NDMI o {worst_val:.3f} w ciągu 15 dni). Zagrożenie hydrologiczne / obumieranie siedlisk!")
                elif worst_val < -0.10:
                    warnings.append(
                        f"<b>Przesuszenie (Natura 2000):</b> Obszar <b>{worst_name}</b> wykazuje znaczący spadek wilgotności (Δ NDMI {worst_val:.3f}).")

                if len(anomalies) > 1:
                    other_sites = ", ".join([f"{x[0]} (Δ{x[1]:.2f})" for x in anomalies[1:5]])
                    warnings.append(f"<b>Inne obszary N2000 z największymi spadkami wilgotności:</b> {other_sites}")
            else:
                ok_status.append("<b>Obszary Natura 2000:</b> Stabilna wilgotność ekosystemów w skali regionu.")
    except Exception as e:
        print(f"Błąd N2000 NDMI: {e}")

    return alerts, warnings, ok_status