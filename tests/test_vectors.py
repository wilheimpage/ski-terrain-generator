from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from ski_terrain.vectors import build_feature_masks, normalise_difficulty


def test_normalise_difficulty():
    assert normalise_difficulty(" Green ", "Unclassified") == "Green"
    assert normalise_difficulty("", "Unclassified") == "Unclassified"
    assert normalise_difficulty(None, "Unclassified") == "Unclassified"
    assert normalise_difficulty(np.nan, "Unclassified") == "Unclassified"
    assert normalise_difficulty(pd.NA, "Unclassified") == "Unclassified"


def test_build_feature_masks_uses_dedicated_lifts_layer(tmp_path):
    gpkg_path = tmp_path / "terrain.gpkg"

    forest = gpd.GeoDataFrame({"name": ["forest"]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])], crs="EPSG:2193")
    road_areas = gpd.GeoDataFrame({"name": ["road_area"]}, geometry=[Polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)])], crs="EPSG:2193")
    roads = gpd.GeoDataFrame({"name": ["main road"]}, geometry=[Polygon([(0.6, 0.6), (1.0, 0.6), (1.0, 1.0), (0.6, 1.0)])], crs="EPSG:2193")
    runs = gpd.GeoDataFrame({"difficulty": ["blue"]}, geometry=[Polygon([(0.2, 0.2), (0.4, 0.2), (0.4, 0.4), (0.2, 0.4)])], crs="EPSG:2193")
    lifts = gpd.GeoDataFrame({"name": ["lift"]}, geometry=[Polygon([(0.2, 0.8), (0.4, 0.8), (0.4, 1.0), (0.2, 1.0)])], crs="EPSG:2193")

    for layer_name, frame in {
        "forest": forest,
        "road_areas": road_areas,
        "roads": roads,
        "ski_runs": runs,
        "lifts": lifts,
    }.items():
        frame.to_file(gpkg_path, layer=layer_name, driver="GPKG")

    grid = SimpleNamespace(
        crs="EPSG:2193",
        valid=np.ones((10, 10), dtype=bool),
        raster_transform=from_origin(0, 10, 1, 1),
        scale_mm_per_world_unit=1.0,
    )
    cfg = {
        "layers": {
            "forest": "forest",
            "road_areas": "road_areas",
            "roads": "roads",
            "ski_runs": "ski_runs",
            "lifts": "lifts",
        },
        "features": {
            "road_name_field": "name",
            "run_difficulty_field": "difficulty",
            "blank_difficulty_label": "Unclassified",
            "roads": {"extrusions": 1},
            "runs": {"extrusions": 1},
            "lifts": {"extrusions": 1},
        },
    }

    masks, counts, widths = build_feature_masks(gpkg_path, grid, cfg)

    assert counts["lifts"] == 1
    assert masks["lifts"].sum() > 0
    assert masks["roads"].sum() > 0
    assert widths["lifts_mm"] > 0


def test_build_feature_masks_treats_missing_layers_as_empty(tmp_path):
    gpkg_path = tmp_path / "terrain.gpkg"

    road_areas = gpd.GeoDataFrame({"name": ["road_area"]}, geometry=[Polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)])], crs="EPSG:2193")
    roads = gpd.GeoDataFrame({"name": ["main road"]}, geometry=[Polygon([(0.6, 0.6), (1.0, 0.6), (1.0, 1.0), (0.6, 1.0)])], crs="EPSG:2193")
    runs = gpd.GeoDataFrame({"difficulty": ["blue"]}, geometry=[Polygon([(0.2, 0.2), (0.4, 0.2), (0.4, 0.4), (0.2, 0.4)])], crs="EPSG:2193")
    lifts = gpd.GeoDataFrame({"name": ["lift"]}, geometry=[Polygon([(0.2, 0.8), (0.4, 0.8), (0.4, 1.0), (0.2, 1.0)])], crs="EPSG:2193")

    for layer_name, frame in {
        "road_areas": road_areas,
        "roads": roads,
        "ski_runs": runs,
        "lifts": lifts,
    }.items():
        frame.to_file(gpkg_path, layer=layer_name, driver="GPKG")

    grid = SimpleNamespace(
        crs="EPSG:2193",
        valid=np.ones((10, 10), dtype=bool),
        raster_transform=from_origin(0, 10, 1, 1),
        scale_mm_per_world_unit=1.0,
    )
    cfg = {
        "layers": {
            "forest": "forest",
            "road_areas": "road_areas",
            "roads": "roads",
            "ski_runs": "ski_runs",
            "lifts": "lifts",
        },
        "features": {
            "road_name_field": "name",
            "run_difficulty_field": "difficulty",
            "blank_difficulty_label": "Unclassified",
            "roads": {"extrusions": 1},
            "runs": {"extrusions": 1},
            "lifts": {"extrusions": 1},
        },
    }

    masks, counts, widths = build_feature_masks(gpkg_path, grid, cfg)

    assert counts["forest"] == 0
    assert counts["lifts"] == 1
    assert masks["forest"].sum() == 0
    assert masks["lifts"].sum() > 0
    assert widths["lifts_mm"] > 0
