import numpy as np
from pathlib import Path
from ski_terrain.config import load_layered_config
from ski_terrain.io import build_paths
from ski_terrain.mesh import component_solid
from ski_terrain.terrain import load_terrain

cfg = load_layered_config(Path('config/projects/example.yml'), Path('config/default.yml'), Path('config/printers/bambu-a1-04.yml'), Path('config/profiles/display.yml'))
paths = build_paths(cfg)
grid = load_terrain(paths.dem, cfg.get('model', {}))
mask = np.zeros_like(grid.valid, dtype=bool)
mask[0, 0] = True
mesh = component_solid(mask, grid, np.zeros_like(grid.z_mm), np.ones_like(grid.z_mm))
print('is_watertight', mesh.is_watertight)
print('is_winding_consistent', mesh.is_winding_consistent)
print('faces', len(mesh.faces))
print('vertices', len(mesh.vertices))
print('vertex_defects', mesh.vertex_defects)
print('euler', mesh.euler_characteristic)
