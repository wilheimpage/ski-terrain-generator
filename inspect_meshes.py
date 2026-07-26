from pathlib import Path
import trimesh
from ski_terrain.config import load_layered_config
from ski_terrain.io import build_paths
from ski_terrain.mesh import build_meshes
from ski_terrain.terrain import classify_rock, load_terrain
from ski_terrain.vectors import build_feature_masks

cfg = load_layered_config(Path('config/projects/example.yml'), Path('config/default.yml'), Path('config/printers/bambu-a1-04.yml'), Path('config/profiles/display.yml'))
paths = build_paths(cfg)
grid = load_terrain(paths.dem, cfg.get('model', {}))
rock, slope, dzdx, dzdy, score = classify_rock(grid, cfg.get('rock', {}), float(cfg.get('model', {}).get('grid_spacing_mm', 0.42)))
masks, counts, widths = build_feature_masks(paths.gpkg, grid, cfg)
parts = build_meshes(grid, rock, masks, cfg)
for mesh, name in parts:
    if mesh is None:
        continue
    print(name)
    print('  watertight:', mesh.is_watertight)
    print('  winding_consistent:', mesh.is_winding_consistent)
    print('  faces:', len(mesh.faces))
    print('  vertices:', len(mesh.vertices))
    try:
        repaired = mesh.process()
        print('  processed watertight:', repaired.is_watertight)
        print('  processed winding_consistent:', repaired.is_winding_consistent)
    except Exception as exc:
        print('  process error:', exc)
    try:
        repaired2 = trimesh.repair.fill_holes(mesh)
        if isinstance(repaired2, tuple):
            repaired2 = repaired2[0]
        print('  fill_holes watertight:', repaired2.is_watertight)
        print('  fill_holes winding_consistent:', repaired2.is_winding_consistent)
    except Exception as exc:
        print('  fill_holes error:', exc)
    try:
        print('  available repair methods:', [name for name in dir(trimesh.repair) if not name.startswith('_')])
    except Exception as exc:
        print('  repair-list error:', exc)
    print()
