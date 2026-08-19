import json
import os
import pyproj
from shapely.geometry import shape, mapping
from shapely.ops import transform


def load_data(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Przeliczanie z polskiego układu metrowego 2180 na stopnie (4326)
    project = pyproj.Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
    for feat in data['features']:
        if feat.get('geometry'):
            geom = shape(feat['geometry'])
            feat['geometry'] = mapping(transform(project, geom))
    return data