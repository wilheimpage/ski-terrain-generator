from __future__ import annotations

from pathlib import Path
from collections import OrderedDict
import numpy as np
import geopandas as gpd
import pandas as pd
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
    return rasterize(
        [(g, 1) for g in geometries],
        out_shape=shape,
        transform=transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)


def buffered_union(frame: gpd.GeoDataFrame, width_world: float):
    geometries = clean_geometries(frame)
    if not geometries:
        return None
    return unary_union(
        [g.buffer(width_world / 2.0, cap_style=2, join_style=2) for g in geometries]
    )


def normalise_difficulty(value, blank_label: str) -> str:
    """Return a stable display label while preserving the source value's spelling."""
    if value is None:
        return blank_label
    try:
        if bool(pd.isna(value)):
            return blank_label
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else blank_label


def ensure_columns(frame: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    return frame


def build_feature_masks(gpkg: Path, grid: TerrainGrid, cfg: dict):
    layers = cfg.get("layers", {})
    features = cfg.get("features", {})
    forest = read_layer(gpkg, str(layers.get("forest", "forest")), grid.crs)
    road_areas = read_layer(gpkg, str(layers.get("road_areas", "road_areas")), grid.crs)
    roads = read_layer(gpkg, str(layers.get("roads", "roads")), grid.crs)
    runs = read_layer(gpkg, str(layers.get("ski_runs", "ski_runs")), grid.crs)
    lifts = read_layer(gpkg, str(layers.get("lifts", "lifts")), grid.crs)

    name_field = str(features.get("road_name_field", "name"))
    difficulty_field = str(features.get("run_difficulty_field", "difficulty"))
    blank_label = str(features.get("blank_difficulty_label", "Unclassified"))

    roads = ensure_columns(roads, [name_field])
    runs = ensure_columns(runs, [difficulty_field])

    shape = grid.valid.shape
    world_per_mm = 1.0 / grid.scale_mm_per_world_unit
    road_width = feature_width_mm(cfg, "roads") * world_per_mm
    run_width = feature_width_mm(cfg, "runs") * world_per_mm
    lift_width = feature_width_mm(cfg, "lifts") * world_per_mm

    forest_m = geometry_mask(clean_geometries(forest), shape, grid.raster_transform)
    roads_m = geometry_mask(buffered_union(roads, road_width), shape, grid.raster_transform)
    roads_m |= geometry_mask(clean_geometries(road_areas), shape, grid.raster_transform)
    lifts_m = geometry_mask(buffered_union(lifts, lift_width), shape, grid.raster_transform)

    # Produce one mask for every distinct difficulty value. Sorting case-insensitively
    # gives repeatable object ordering without imposing any recognised-value list.
    labels = runs[difficulty_field].map(lambda value: normalise_difficulty(value, blank_label))
    distinct_labels = sorted(labels.unique().tolist(), key=lambda value: (value.casefold(), value))
    run_masks: OrderedDict[str, np.ndarray] = OrderedDict()
    run_counts: OrderedDict[str, int] = OrderedDict()
    for label in distinct_labels:
        subset = runs[labels == label]
        mask = geometry_mask(buffered_union(subset, run_width), shape, grid.raster_transform)
        mask &= grid.valid
        run_masks[label] = mask
        run_counts[label] = int(len(subset))

    for mask in (forest_m, roads_m, lifts_m):
        mask &= grid.valid

    counts = {
        "forest": len(forest),
        "road_areas": len(road_areas),
        "roads": len(roads),
        "lifts": len(lifts),
        "ski_runs": len(runs),
        "ski_runs_by_difficulty": dict(run_counts),
    }
    widths = {
        "roads_mm": road_width / world_per_mm,
        "runs_mm": run_width / world_per_mm,
        "lifts_mm": lift_width / world_per_mm,
    }
    return {
        "forest": forest_m,
        "roads": roads_m,
        "lifts": lifts_m,
        "runs": run_masks,
    }, counts, widths
