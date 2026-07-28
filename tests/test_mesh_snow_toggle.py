import numpy as np

from ski_terrain.mesh import build_meshes
from ski_terrain.terrain import TerrainGrid


def test_build_meshes_can_skip_snow_part_when_disabled():
    grid = TerrainGrid(
        crs=None,
        source_transform=None,
        raster_transform=None,
        elev=np.array([[10.0, 10.5], [11.0, 11.5]], dtype=np.float32),
        valid=np.array([[True, True], [True, True]], dtype=bool),
        x_mm=np.array([0.0, 1.0], dtype=np.float32),
        y_mm=np.array([1.0, 0.0], dtype=np.float32),
        z_mm=np.array([[10.0, 10.5], [11.0, 11.5]], dtype=np.float32),
        width_mm=1.0,
        height_mm=1.0,
        scale_mm_per_world_unit=1.0,
        dx_world=1.0,
        dy_world=1.0,
    )
    masks = {
        "forest": np.zeros((2, 2), dtype=bool),
        "roads": np.zeros((2, 2), dtype=bool),
        "lifts": np.zeros((2, 2), dtype=bool),
        "runs": {},
    }
    cfg = {
        "model": {"include_snow": False, "base_thickness_mm": 3.0, "material_cap_depth_mm": 0.8},
        "features": {},
        "layers": {},
    }

    parts = build_meshes(grid, np.zeros((2, 2), dtype=bool), masks, cfg)

    assert all(name != "Snow" for _, name in parts)
