from __future__ import annotations

import json
from pathlib import Path
import sys
import trimesh

from .config import feature_width_mm
from .io import build_paths, inspect_qgz
from .mesh import assembled_3mf, build_meshes, export_parts
from .preview import save_preview
from .terrain import classify_rock, load_terrain
from .vectors import build_feature_masks


def _log_progress(message: str) -> None:
    print(f"[ski-terrain] {message}", file=sys.stderr)


def run_build(cfg: dict, mode: str = "full") -> dict:
    paths = build_paths(cfg)
    model_cfg = cfg.get("model", {})
    _log_progress(f"Loading terrain from {paths.dem}")
    grid = load_terrain(paths.dem, model_cfg)
    grid_spacing = float(model_cfg.get("grid_spacing_mm", 0.42))
    _log_progress("Classifying rock and slope")
    rock, slope, dzdx, dzdy, score = classify_rock(grid, cfg.get("rock", {}), grid_spacing)
    _log_progress("Building feature masks from GeoPackage")
    masks, counts, widths = build_feature_masks(paths.gpkg, grid, cfg)
    _log_progress("Inspecting QGIS project metadata")
    project_info = inspect_qgz(paths.qgz)
    report = {
        "inputs": {"dem":str(paths.dem),"gpkg":str(paths.gpkg),"qgz":str(paths.qgz) if paths.qgz else None},
        "qgz_info": project_info,
        "model": {"width_mm":grid.width_mm,"height_mm":grid.height_mm,"maximum_z_mm":float(grid.z_mm.max()),
                  "grid_spacing_mm":grid_spacing,"vertical_exaggeration":float(model_cfg.get("vertical_exaggeration",1.0))},
        "feature_widths": widths,
        "feature_counts": counts,
        "rock": {"coverage_percent": float(rock.sum() / grid.valid.sum() * 100.0)},
        "outputs": {}
    }
    if mode == "validate":
        return report
    preview_path = paths.output_dir / f"{paths.stem}_preview.png"
    _log_progress(f"Writing preview to {preview_path}")
    save_preview(preview_path, f"{paths.stem} — {grid.width_mm:.1f} × {grid.height_mm:.1f} mm",
                 grid.valid, rock, masks, slope, dzdx, dzdy, score,
                 bool(cfg.get("output", {}).get("diagnostic_previews", False)))
    report["outputs"]["preview"] = str(preview_path)
    if mode == "preview":
        report_path = paths.output_dir / f"{paths.stem}_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["outputs"]["report"] = str(report_path)
        return report
    _log_progress("Building mesh parts")
    parts = build_meshes(grid, rock, masks, cfg)
    scene = trimesh.Scene()
    part_report = []
    for mesh, name in parts:
        if mesh is None: continue
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        part_report.append({"name":name,"vertices":int(len(mesh.vertices)),"faces":int(len(mesh.faces)),
                            "watertight":bool(mesh.is_watertight),"winding_consistent":bool(mesh.is_winding_consistent)})
    output_3mf = paths.output_dir / f"{paths.stem}.3mf"
    _log_progress(f"Writing 3MF to {output_3mf}")
    assembled_3mf(scene, output_3mf, f"{paths.stem} assembled model")
    report["parts"] = part_report
    report["outputs"]["3mf"] = str(output_3mf)
    if bool(cfg.get("output", {}).get("write_stl_parts", True)):
        parts_dir = paths.output_dir / f"{paths.stem}_parts"
        _log_progress(f"Writing STL parts to {parts_dir}")
        export_parts(parts, parts_dir)
        report["outputs"]["parts"] = str(parts_dir)
    report_path = paths.output_dir / f"{paths.stem}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["outputs"]["report"] = str(report_path)
    return report
