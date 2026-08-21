# inspector.py

import ee
import datetime
import pandas as pd


def run_regional_inspection():
    """
    Wykonuje automatyczne skanowanie całego obszaru (Zachodniopomorskie)
    pod kątem anomalii środowiskowych.
    """
    alerts = []
    warnings = []
    ok_status = []

    end_date = ee.Date(datetime.date.today().isoformat())
    region_zach = ee.Geometry.Rectangle([14.0, 52.6, 17.0, 54.6])  # Zachodniopomorskie

    # ---------------------------------------------------------
    # 1. POWIETRZE (S5P) - Skrajne zanieczyszczenia (ostatnie 3 dni)
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
            val_dict = img.reduceRegion(reducer=ee.Reducer.max(), geometry=region_zach, scale=5000,
                                        bestEffort=True).getInfo()
            val = val_dict.get(band)

            if val:
                if val >= thr_alert:
                    alerts.append(
                        f"**{name}:** Krytyczne stężenie w regionie! Zarejestrowane maksimum: {val:.5f} mol/m².")
                elif val >= thr_warn:
                    warnings.append(f"**{name}:** Podwyższone stężenie (Maksimum: {val:.5f} mol/m²).")
                else:
                    ok_status.append(f"**{name}:** W normie (Max: {val:.5f}).")
        except Exception as e:
            pass

    # ---------------------------------------------------------
    # 2. JAKOŚĆ WÓD (NDCI) - Zagrożenie zakwitem / złotą algą
    # ---------------------------------------------------------
    try:
        start_water = end_date.advance(-10, 'day')
        zalew = ee.Geometry.Rectangle([14.1, 53.4, 14.8, 54.0])  # Zalew Szczeciński / Odra

        s2_water = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(zalew).filterDate(start_water, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))

        if s2_water.size().getInfo() > 0:
            img = s2_water.mosaic()
            ndwi = img.normalizedDifference(['B3', 'B8'])
            water_mask = ndwi.gt(0.1)
            ndci = img.normalizedDifference(['B5', 'B4']).updateMask(water_mask)

            max_ndci = ndci.reduceRegion(reducer=ee.Reducer.max(), geometry=zalew, scale=100, bestEffort=True).get(
                'nd').getInfo()

            if max_ndci is not None:
                if max_ndci > 0.12:
                    alerts.append(
                        f"**Wody powierzchniowe (Odra/Zalew):** Ekstremalnie wysoki wskaźnik NDCI ({max_ndci:.3f}). Bardzo wysokie ryzyko masowego zakwitu toksycznych glonów (np. złotej algi). Wskazana pilna inspekcja terenowa!")
                elif max_ndci > 0.05:
                    warnings.append(
                        f"**Wody powierzchniowe (Odra/Zalew):** Podwyższony poziom chlorofilu-a (NDCI: {max_ndci:.3f}). Możliwe początki zakwitów.")
                else:
                    ok_status.append(
                        f"**Jakość wód (NDCI):** Stabilna, brak sygnatur rozległych zakwitów (Max NDCI: {max_ndci:.3f}).")
    except Exception as e:
        pass

    # ---------------------------------------------------------
    # 3. WILGOTNOŚĆ (NDMI) - Błyskawiczna susza / Blokady
    # ---------------------------------------------------------
    try:
        mid_date = end_date.advance(-15, 'day')
        start_moisture = mid_date.advance(-15, 'day')
        s2_moisture = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region_zach)

        recent_ndmi = s2_moisture.filterDate(mid_date, end_date).median().normalizedDifference(['B8', 'B11'])
        past_ndmi = s2_moisture.filterDate(start_moisture, mid_date).median().normalizedDifference(['B8', 'B11'])

        diff = recent_ndmi.subtract(past_ndmi)
        # Szukamy najgłębszego spadku wilgotności
        min_diff = diff.reduceRegion(reducer=ee.Reducer.min(), geometry=region_zach, scale=1000, bestEffort=True).get(
            'nd').getInfo()

        if min_diff is not None:
            if min_diff < -0.2:
                alerts.append(
                    f"**Anomalia Wilgotności (NDMI):** Wykryto drastyczne spadki wilgotności terenu (o {min_diff:.3f}). Ryzyko 'flash drought' (błyskawicznej suszy) lub zatorów na dopływach!")
            elif min_diff < -0.1:
                warnings.append(
                    f"**Anomalia Wilgotności:** Miejscowe przesuszenie terenu (spadek NDMI o {min_diff:.3f}).")
            else:
                ok_status.append("**Wilgotność ekosystemów:** Zrównoważona, brak gwałtownych skoków przesuszenia.")
    except Exception as e:
        pass

    return alerts, warnings, ok_status