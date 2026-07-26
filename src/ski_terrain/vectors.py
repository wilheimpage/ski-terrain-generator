from __future__ import annotations

import re
from pathlib import Path
import numpy as np
import geopandas as gpd
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .config import feature_width_mm
from .errors import BuildError
from .io import clean_geometries, read_layer
from .terrain import TerrainGrid


def geometry_mask(geometry, shape, transform) -> np.ndarray:
    if geometry is None:
        return np.zeros(shape, dtype=bool)
    if isinstance(geometry, BaseGeometry):
        geometries = [] if geometry.is_empty else [geometry]
    else:
        geometries = [g for g in geometry if g is not None and not g.is_empty]
    if not geometries:
        return np.zeros(shape, dtype=bool)
    return rasterize([(g, 1) for g in geometries], out_shape=shape, transform=transform,
                     fill=0, all_touched=True, dtype="uint8").astype(bool)


def buffered_union(frame: gpd.GeoDataFrame, width_world: float):
    geometries = clean_geometries(frame)
    if not geometries:
        return None
    return unary_union([g.buffer(width_world / 2.0, cap_style=2, join_style=2) for g in geometries])


def regex_mask(values, patterns: list[str]) -> np.ndarray:
    expressions = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    return np.asarray([any(rx.search(str(value or "").strip()) for rx in expressions) for value in values])


def build_feature_masks(gpkg: Path, grid: TerrainGrid, cfg: dict):
    layers = cfg.get("layers", {})
    features = cfg.get("features", {})
    forest = read_layer(gpkg, str(layers.get("forest", "forest")), grid.crs)
    road_areas = read_layer(gpkg, str(layers.get("road_areas", "road_areas")), grid.crs)
    roads = read_layer(gpkg, str(layers.get("roads", "roads")), grid.crs)
    runs = read_layer(gpkg, str(layers.get("ski_runs", "ski_runs")), grid.crs)
    name_field = str(features.get("road_name_field", "name"))
    difficulty_field = str(features.get("run_difficulty_field", "difficulty"))
    if name_field not in roads.columns:
        raise BuildError(f"Road layer lacks field '{name_field}'")
    if difficulty_field not in runs.columns:
        raise BuildError(f"Ski-run layer lacks field '{difficulty_field}'")
    patterns = list(features.get("lift_name_patterns", ["^access( tow)?$", "^middle$", "^jarman$"]))
    is_lift = regex_mask(roads[name_field].fillna(""), patterns)
    lifts = roads[is_lift].copy()
    roads_only = roads[~is_lift].copy()
    shape = grid.valid.shape
    world_per_mm = 1.0 / grid.scale_mm_per_world_unit
    road_width = feature_width_mm(cfg, "roads") * world_per_mm
    run_width = feature_width_mm(cfg, "runs") * world_per_mm
    lift_width = feature_width_mm(cfg, "lifts") * world_per_mm
    forest_m = geometry_mask(clean_geometries(forest), shape, grid.raster_transform)
    roads_m = geometry_mask(buffered_union(roads_only, road_width), shape, grid.raster_transform)
    roads_m |= geometry_mask(clean_geometries(road_areas), shape, grid.raster_transform)
    lifts_m = geometry_mask(buffered_union(lifts, lift_width), shape, grid.raster_transform)
    difficulty = runs[difficulty_field].fillna("black").astype(str).str.strip().str.lower()
    blue_values = {str(v).strip().lower() for v in features.get("blue_difficulty_values", ["blue"])}
    is_blue = difficulty.isin(blue_values)
    blue_m = geometry_mask(buffered_union(runs[is_blue], run_width), shape, grid.raster_transform)
    black_m = geometry_mask(buffered_union(runs[~is_blue], run_width), shape, grid.raster_transform) | lifts_m
    for mask in (forest_m, roads_m, blue_m, black_m):
        mask &= grid.valid
    counts = {"forest": len(forest), "road_areas": len(road_areas), "roads": len(roads_only),
              "lifts": len(lifts), "ski_runs": len(runs)}
    widths = {"roads_mm": road_width / world_per_mm, "runs_mm": run_width / world_per_mm,
              "lifts_mm": lift_width / world_per_mm}
    return {"forest": forest_m, "roads": roads_m, "blue": blue_m, "black": black_m}, counts, widths
