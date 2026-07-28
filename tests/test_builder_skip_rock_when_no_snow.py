from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

from ski_terrain.builder import run_build
from ski_terrain.config import load_layered_config


def test_run_build_skips_rock_classification_when_snow_disabled(tmp_path):
    dem_path = tmp_path / "terrain.tif"
    gpkg_path = tmp_path / "terrain.gpkg"
    qgz_path = tmp_path / "terrain.qgz"
    gpkg_path.write_bytes(b"dummy")
    qgz_path.write_bytes(b"dummy")

    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0.0, 2.0, 1.0, 1.0),
    ) as dst:
        dst.write(np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32), 1)

    project_path = tmp_path / "project.yml"
    project_path.write_text(
        "inputs:\n"
        "  dem: ./terrain.tif\n"
        "  gpkg: ./terrain.gpkg\n"
        "  qgz: ./terrain.qgz\n"
        "model:\n"
        "  include_snow: false\n"
        "output:\n"
        "  directory: ./output\n"
        "  stem: terrain\n",
        encoding="utf-8",
    )

    cfg = load_layered_config(project_path)
    with patch("ski_terrain.builder.build_feature_masks", return_value=({}, {}, {})), patch(
        "ski_terrain.builder.inspect_qgz", return_value={"provided": False, "project": "", "layers": []}
    ):
        report = run_build(cfg, mode="validate")

    assert report["rock"]["coverage_percent"] == 0.0
