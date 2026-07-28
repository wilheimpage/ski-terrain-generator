from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import trimesh

from .errors import BuildError
from .terrain import load_terrain


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert a GeoTIFF DEM to a single OBJ or STL mesh")
    p.add_argument("input", type=Path, help="Input GeoTIFF DEM path")
    p.add_argument("--output", type=Path, help="Output mesh path (default: <input stem>.obj or .stl)")
    p.add_argument("--format", choices=("obj", "stl"), default="obj", help="Output mesh format")
    p.add_argument("--max-dimension", type=float, default=250.0, help="Maximum output dimension in millimetres")
    p.add_argument("--vertical-scale", type=float, default=1.0, help="Vertical exaggeration")
    p.add_argument("--base-thickness", type=float, default=3.0, help="Flat base thickness in millimetres")
    return p


def _build_mesh(grid) -> trimesh.Trimesh:
    rows, cols = grid.z_mm.shape
    if rows < 2 or cols < 2:
        raise BuildError("DEM must contain at least 2x2 cells for mesh generation")

    top_vertices = []
    for r in range(rows):
        for c in range(cols):
            top_vertices.append((float(grid.x_mm[c]), float(grid.y_mm[r]), float(grid.z_mm[r, c])))

    bottom_vertices = [(x, y, 0.0) for x, y, _ in top_vertices]
    vertices = np.array(top_vertices + bottom_vertices, dtype=np.float64)

    faces = []
    def index(r: int, c: int, bottom: bool = False) -> int:
        offset = rows * cols
        idx = r * cols + c
        return idx if not bottom else offset + idx

    for r in range(rows - 1):
        for c in range(cols - 1):
            a = index(r, c)
            b = index(r, c + 1)
            d = index(r + 1, c + 1)
            e = index(r + 1, c)
            faces.append((a, b, d))
            faces.append((a, d, e))

            ab = index(r, c, bottom=True)
            bb = index(r, c + 1, bottom=True)
            db = index(r + 1, c + 1, bottom=True)
            eb = index(r + 1, c, bottom=True)
            faces.append((ab, db, bb))
            faces.append((ab, eb, db))

    def add_quad(a: int, b: int, c: int, d: int) -> None:
        faces.append((a, b, c))
        faces.append((a, c, d))

    for c in range(cols - 1):
        top_a = index(0, c)
        top_b = index(0, c + 1)
        bot_a = index(0, c, bottom=True)
        bot_b = index(0, c + 1, bottom=True)
        add_quad(top_a, top_b, bot_b, bot_a)

        top_a = index(rows - 1, c)
        top_b = index(rows - 1, c + 1)
        bot_a = index(rows - 1, c, bottom=True)
        bot_b = index(rows - 1, c + 1, bottom=True)
        add_quad(top_a, top_b, bot_b, bot_a)

    for r in range(rows - 1):
        top_a = index(r, 0)
        top_b = index(r + 1, 0)
        bot_a = index(r, 0, bottom=True)
        bot_b = index(r + 1, 0, bottom=True)
        add_quad(top_a, top_b, bot_b, bot_a)

        top_a = index(r, cols - 1)
        top_b = index(r + 1, cols - 1)
        bot_a = index(r, cols - 1, bottom=True)
        bot_b = index(r + 1, cols - 1, bottom=True)
        add_quad(top_a, top_b, bot_b, bot_a)

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=False)
    mesh.remove_unreferenced_vertices()
    try:
        mesh = mesh.process()
    except Exception:
        mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    return mesh


def convert_dem(input_path: Path, output_path: Path, *, max_dimension: float, vertical_scale: float, base_thickness: float, output_format: str) -> Path:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input DEM not found: {input_path}")

    model_cfg = {
        "maximum_dimension_mm": float(max_dimension),
        "grid_spacing_mm": 0.42,
        "base_thickness_mm": float(base_thickness),
        "vertical_exaggeration": float(vertical_scale),
    }
    grid = load_terrain(input_path, model_cfg)
    mesh = _build_mesh(grid)

    if output_path is None:
        output_path = input_path.with_suffix("." + output_format)
    else:
        output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_path)
    return output_path


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.output is None:
        output_path = args.input.with_suffix(f".{args.format}")
    else:
        output_path = args.output
    try:
        result = convert_dem(
            args.input,
            output_path,
            max_dimension=args.max_dimension,
            vertical_scale=args.vertical_scale,
            base_thickness=args.base_thickness,
            output_format=args.format,
        )
    except (BuildError, FileNotFoundError, OSError) as exc:
        print(f"ERROR: {exc}", flush=True)
        return 2

    print(f"Wrote {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
