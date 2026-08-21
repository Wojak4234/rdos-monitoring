# inspector.py

import ee
import datetime
from shapely.geometry import shape


def run_regional_inspection(n2000_features=None):
    """
    Wykonuje zaawansowane skanowanie przestrzenne całego regionu (Zachodniopomorskie)
    wykrywając nie tylko same anomalie, ale też ich dokładne współrzędne i obszary N2000.
    """
    alerts = []
    warnings = []
    ok_status = []

    end_date = ee.Date(datetime.date.today().isoformat())
    region_zach = ee.Geometry.Rectangle([14.0, 52.6, 17.0, 54.6])

    # ---------------------------------------------------------
    # 1. POWIETRZE (S5P) - Skrajne zanieczyszczenia z geolokalizacją
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
                # Wyszukiwanie współrzędnych piksela o maksymalnej wartości
                mask = img.gte(ee.Number(val).subtract(0.000001))
                coords = ee.Image.pixelLonLat().updateMask(mask).reduceRegion(reducer=ee.Reducer.first(),
                                                                              geometry=region_zach,
                                                                              scale=5000).getInfo()
                lat, lon = coords.get('latitude'), coords.get('longitude')

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat else "Brak dokładnych danych geolokalizacyjnych"
                gmaps_link = f" - [🗺️ Pokaż na mapie](https://www.google.com/maps/search/?api=1&query={lat},{lon})" if lat else ""

                if val >= thr_alert:
                    alerts.append(
                        f"**{name}:** Krytyczne stężenie! Zarejestrowane maksimum: **{val:.5f} mol/m²**. Lokalizacja epicentrum zanieczyszczeń: {loc_str}{gmaps_link}")
                else:
                    warnings.append(
                        f"**{name}:** Podwyższone stężenie (Maksimum: {val:.5f} mol/m²). Lokalizacja: {loc_str}{gmaps_link}")
            elif val:
                ok_status.append(f"**{name}:** W normie (Max: {val:.5f}).")
        except Exception as e:
            print(f"Błąd S5P: {e}")

    # ---------------------------------------------------------
    # 2. JAKOŚĆ WÓD (NDCI) - Zagrożenie zakwitem / złotą algą
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
                # Lokalizacja największego zakwitu w regionie
                mask = ndci.gte(ee.Number(max_ndci).subtract(0.01))
                coords = ee.Image.pixelLonLat().updateMask(mask).reduceRegion(reducer=ee.Reducer.first(),
                                                                              geometry=region_zach, scale=100).getInfo()
                lat, lon = coords.get('latitude'), coords.get('longitude')

                loc_str = f"Współrzędne: {lat:.4f}, {lon:.4f}" if lat else ""
                gmaps_link = f" - [🗺️ Sprawdź lokalizację](https://www.google.com/maps/search/?api=1&query={lat},{lon})" if lat else ""

                if max_ndci > 0.12:
                    alerts.append(
                        f"**Wody powierzchniowe (Chlorofil-a):** Ekstremalnie wysoki wskaźnik NDCI (**{max_ndci:.3f}**). Bardzo wysokie ryzyko masowego zakwitu toksycznych glonów (np. złotej algi). Wskazana pilna inspekcja w miejscu: {loc_str}{gmaps_link}")
                else:
                    warnings.append(
                        f"**Wody powierzchniowe:** Podwyższony chlorofil-a (NDCI: {max_ndci:.3f}). Zwiększona masa materii organicznej. {loc_str}{gmaps_link}")
            elif max_ndci:
                ok_status.append(
                    f"**Jakość wód (NDCI):** Stabilna, brak sygnatur rozległych zakwitów (Max NDCI w regionie: {max_ndci:.3f}).")
    except Exception as e:
        print(f"Błąd Wody: {e}")

    # ---------------------------------------------------------
    # 3. WILGOTNOŚĆ (NDMI) - Błyskawiczna susza i Skan Natura 2000
    # ---------------------------------------------------------
    try:
        if n2000_features:
            points = []
            for f in n2000_features:
                name = f['properties'].get('nazwa', f['properties'].get('SITE_NAME', 'Nieznany Obszar'))
                c = shape(f['geometry']).centroid  # Zamiana poligonu na centroid w locie
                points.append(ee.Feature(ee.Geometry.Point([c.x, c.y]), {'name': name}))

            fc = ee.FeatureCollection(points)

            # Buforowanie o 1km wokół centrum obszaru, żeby nie analizować tylko jednego piksela
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

            # Ściągnięcie średnich wartości różnicy NDMI dla KAŻDEGO obszaru N2000 do Pythona!
            results = diff.reduceRegions(collection=fc_buf, reducer=ee.Reducer.mean(), scale=100).getInfo()

            anomalies = []
            for feat in results.get('features', []):
                d = feat['properties'].get('mean')
                n = feat['properties'].get('name')
                if d is not None and d < -0.05:  # Analizujemy tylko spadki
                    anomalies.append((n, d))

            if anomalies:
                # Sortowanie od największych spadków
                anomalies.sort(key=lambda x: x[1])
                worst_name, worst_val = anomalies[0]

                if worst_val < -0.15:
                    alerts.append(
                        f"**Błyskawiczna Susza (Natura 2000):** Obszar **{worst_name}** odnotował drastyczny spadek wilgotności (spadek NDMI o {worst_val:.3f} w ciągu 15 dni). Zagrożenie hydrologiczne / obumieranie siedlisk!")
                elif worst_val < -0.10:
                    warnings.append(
                        f"**Przesuszenie (Natura 2000):** Obszar **{worst_name}** wykazuje znaczący spadek wilgotności (Δ NDMI {worst_val:.3f}).")

                # Dodanie listy innych obszarów zagrożonych
                if len(anomalies) > 1:
                    other_sites = ", ".join([f"{x[0]} (Δ{x[1]:.2f})" for x in anomalies[1:5]])  # Maksymalnie 4 inne
                    warnings.append(f"**Inne obszary N2000 z największymi spadkami wilgotności:** {other_sites}")
            else:
                ok_status.append("**Obszary Natura 2000:** Stabilna wilgotność ekosystemów w skali regionu.")
    except Exception as e:
        print(f"Błąd N2000 NDMI: {e}")

    return alerts, warnings, ok_status