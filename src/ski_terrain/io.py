from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from .errors import BuildError


@dataclass(frozen=True)
class BuildPaths:
    dem: Path
    gpkg: Path
    qgz: Path | None
    output_dir: Path
    stem: str


def build_paths(cfg: dict) -> BuildPaths:
    inputs = cfg.get("inputs", {})
    output = cfg.get("output", {})
    dem = Path(str(inputs.get("dem", "")))
    gpkg = Path(str(inputs.get("gpkg", "")))
    qgz_raw = inputs.get("qgz")
    qgz = Path(str(qgz_raw)) if qgz_raw else None
    output_dir = Path(str(output.get("directory", "output")))
    stem = str(output.get("stem", "ski_terrain"))
    for path, label in ((dem, "DEM"), (gpkg, "GeoPackage")):
        if not path.exists():
            raise BuildError(f"{label} not found: {path}")
    if qgz and not qgz.exists():
        raise BuildError(f"QGIS project not found: {qgz}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return BuildPaths(dem, gpkg, qgz, output_dir, stem)


def inspect_qgz(path: Path | None) -> dict:
    if path is None:
        return {"provided": False}
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".qgs")]
            if not names:
                return {"provided": True, "warning": "No .qgs XML found inside QGZ"}
            root = ET.fromstring(archive.read(names[0]))
            layers = sorted({e.text for e in root.findall(".//layername") if e.text})
            return {"provided": True, "project": root.attrib.get("projectname", path.stem), "layers": layers}
    except Exception as exc:
        return {"provided": True, "warning": f"Could not inspect QGZ: {exc}"}


def read_layer(gpkg: Path, name: str, target_crs) -> gpd.GeoDataFrame:
    try:
        frame = gpd.read_file(gpkg, layer=name)
    except Exception as exc:
        raise BuildError(f"Could not read layer '{name}': {exc}") from exc
    if frame.crs is None:
        raise BuildError(f"Layer '{name}' has no CRS")
    return frame.to_crs(target_crs)


def clean_geometries(frame: gpd.GeoDataFrame) -> list[BaseGeometry]:
    geometries: list[BaseGeometry] = []
    for geometry in frame.geometry:
        if geometry is None or geometry.is_empty:
            continue
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if not geometry.is_empty:
            geometries.append(geometry)
    return geometries
