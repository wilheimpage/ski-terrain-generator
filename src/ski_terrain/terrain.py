from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from scipy.ndimage import binary_closing, binary_opening, gaussian_filter, label as ndi_label

from .errors import BuildError


@dataclass
class TerrainGrid:
    crs: object
    source_transform: Affine
    raster_transform: Affine
    elev: np.ndarray
    valid: np.ndarray
    x_mm: np.ndarray
    y_mm: np.ndarray
    z_mm: np.ndarray
    width_mm: float
    height_mm: float
    scale_mm_per_world_unit: float
    dx_world: float
    dy_world: float


def load_terrain(path: Path, model_cfg: dict) -> TerrainGrid:
    maximum = float(model_cfg.get("maximum_dimension_mm", 250.0))
    grid_mm = float(model_cfg.get("grid_spacing_mm", 0.42))
    base_mm = float(model_cfg.get("base_thickness_mm", 3.0))
    vertical = float(model_cfg.get("vertical_exaggeration", 1.0))
    with rasterio.open(path) as src:
        if src.crs is None:
            raise BuildError("DEM has no CRS")
        transform = src.transform
        col_world = float(np.hypot(transform.a, transform.d))
        row_world = float(np.hypot(transform.b, transform.e))
        world_w = (src.width - 1) * col_world
        world_h = (src.height - 1) * row_world
        scale = maximum / max(world_w, world_h)
        width_mm, height_mm = world_w * scale, world_h * scale
        out_w = int(round(width_mm / grid_mm)) + 1
        out_h = int(round(height_mm / grid_mm)) + 1
        elevation = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.bilinear, masked=True).astype(np.float32)
        valid = ~np.ma.getmaskarray(elevation)
        elev = np.asarray(elevation.filled(np.nan), dtype=np.float32)
        raster_transform = transform * Affine.scale(src.width / out_w, src.height / out_h)
        crs = src.crs
    if not valid.any():
        raise BuildError("DEM contains no valid elevation cells")
    if not valid.all():
        elev = np.where(valid, elev, np.nanmedian(elev[valid]))
    x_mm = np.linspace(0.0, width_mm, out_w, dtype=np.float32)
    y_mm = np.linspace(height_mm, 0.0, out_h, dtype=np.float32)
    z_mm = base_mm + (elev - float(np.nanmin(elev[valid]))) * scale * vertical
    return TerrainGrid(crs, transform, raster_transform, elev, valid, x_mm, y_mm, z_mm,
                       width_mm, height_mm, scale, world_w / (out_w - 1), world_h / (out_h - 1))


def classify_rock(grid: TerrainGrid, cfg: dict, grid_spacing_mm: float):
    dzdy, dzdx = np.gradient(grid.elev, grid.dy_world, grid.dx_world)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    local = gaussian_filter(grid.elev, sigma=float(cfg.get("roughness_sigma_cells", 1.2)))
    rough = np.abs(grid.elev - local)
    percentile = float(cfg.get("roughness_normalization_percentile", 95.0))
    denominator = max(float(np.percentile(rough[grid.valid], percentile)), 0.01)
    rough_n = np.clip(rough / denominator, 0.0, 1.0)
    center = float(cfg.get("slope_center_degrees", 42.75))
    span = float(cfg.get("slope_span_degrees", 13.25))
    rough_weight = float(cfg.get("roughness_weight", 0.575))
    threshold = float(cfg.get("score_threshold", 0.65))
    score = (slope - center) / span + rough_weight * rough_n
    rock = grid.valid & (score > threshold)
    close_n = int(cfg.get("closing_iterations", 1))
    open_n = int(cfg.get("opening_iterations", 1))
    if close_n:
        rock = binary_closing(rock, np.ones((3, 3), dtype=bool), iterations=close_n) & grid.valid
    if open_n:
        cross = np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=bool)
        rock = binary_opening(rock, cross, iterations=open_n) & grid.valid
    labels, _ = ndi_label(rock, structure=np.ones((3,3), dtype=np.uint8))
    minimum_area = float(cfg.get("minimum_patch_area_mm2", 1.5))
    minimum_cells = max(1, int(round(minimum_area / (grid_spacing_mm ** 2))))
    counts = np.bincount(labels.ravel())
    keep = counts >= minimum_cells
    keep[0] = False
    return keep[labels] & grid.valid, slope, dzdx, dzdy, score
