from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import trimesh

from .errors import BuildError
from .terrain import TerrainGrid
from .config import surface_layer_depth_mm

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


def to_cells(mask):
    return mask[:-1,:-1] | mask[:-1,1:] | mask[1:,:-1] | mask[1:,1:]


def component_solid(cell_mask, grid: TerrainGrid, bottom_z, top_z):
    rr, cc = np.nonzero(cell_mask)
    if len(rr) == 0:
        return None
    keys = np.concatenate([np.stack([rr,cc],1), np.stack([rr,cc+1],1),
                           np.stack([rr+1,cc],1), np.stack([rr+1,cc+1],1)], axis=0)
    unique = np.unique(keys, axis=0)
    ids = {(int(r), int(c)): i for i, (r,c) in enumerate(unique)}
    n = len(unique)
    top = np.column_stack([grid.x_mm[unique[:,1]], grid.y_mm[unique[:,0]], top_z[unique[:,0], unique[:,1]]])
    bottom = np.column_stack([grid.x_mm[unique[:,1]], grid.y_mm[unique[:,0]], bottom_z[unique[:,0], unique[:,1]]])
    vertices = np.vstack([top, bottom])
    faces = []
    height, width = cell_mask.shape
    for r0, c0 in zip(rr, cc):
        r, c = int(r0), int(c0)
        a,b,d,e = ids[(r,c)], ids[(r,c+1)], ids[(r+1,c)], ids[(r+1,c+1)]
        faces.extend(((a,d,b),(b,d,e),(a+n,b+n,d+n),(b+n,e+n,d+n)))
        edges = []
        if r == 0 or not cell_mask[r-1,c]: edges.append(((r,c),(r,c+1)))
        if r == height-1 or not cell_mask[r+1,c]: edges.append(((r+1,c+1),(r+1,c)))
        if c == 0 or not cell_mask[r,c-1]: edges.append(((r+1,c),(r,c)))
        if c == width-1 or not cell_mask[r,c+1]: edges.append(((r,c+1),(r+1,c+1)))
        for p,q in edges:
            ia,ib = ids[p],ids[q]
            faces.extend(((ia,ib,ia+n),(ib,ib+n,ia+n)))
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=False)
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) > 0:
        try:
            mesh = mesh.process()
        except Exception:
            mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    return mesh


def named_solid(name, mask, grid, bottom, top):
    mesh = component_solid(mask, grid, bottom, top)
    if mesh is not None:
        mesh.metadata["name"] = name
    return mesh


def repair_mesh(mesh: trimesh.Trimesh | None) -> trimesh.Trimesh | None:
    if mesh is None or len(mesh.faces) == 0:
        return mesh
    try:
        return mesh.process()
    except Exception:
        return mesh


def assembled_3mf(scene: trimesh.Scene, output_path: Path, name: str):
    temporary = output_path.with_name(output_path.stem + "_unassembled.3mf")
    scene.export(temporary)
    ET.register_namespace("", CORE_NS)
    ET.register_namespace("p", PROD_NS)
    with zipfile.ZipFile(temporary, "r") as source:
        model_name = "3D/3dmodel.model"
        root = ET.fromstring(source.read(model_name))
        resources = root.find(f"{{{CORE_NS}}}resources")
        build = root.find(f"{{{CORE_NS}}}build")
        if resources is None or build is None:
            raise BuildError("Unexpected 3MF structure")
        children = resources.findall(f"{{{CORE_NS}}}object")
        if not children:
            raise BuildError("No 3MF objects found to assemble")
        parent_id = str(max(int(obj.attrib["id"]) for obj in children) + 1)
        parent = ET.SubElement(resources, f"{{{CORE_NS}}}object", {"id":parent_id,"name":name,"type":"model"})
        components = ET.SubElement(parent, f"{{{CORE_NS}}}components")
        for obj in children:
            obj_name = obj.attrib.get("name") or obj.attrib.get("id") or "unnamed"
            ET.SubElement(components, f"{{{CORE_NS}}}component", {"objectid":obj.attrib["id"], "transform": "1 0 0 0 1 0 0 0 1 0 0 0"})
            if obj_name:
                obj.set("name", obj_name)
        for item in list(build):
            build.remove(item)
        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid":parent_id})
        xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as target:
            for info in source.infolist():
                target.writestr(info, xml if info.filename == model_name else source.read(info.filename))
    temporary.unlink(missing_ok=True)


def build_meshes(grid: TerrainGrid, rock, masks, cfg: dict):
    valid_c = grid.valid[:-1,:-1] & grid.valid[:-1,1:] & grid.valid[1:,:-1] & grid.valid[1:,1:]
    rock_c = to_cells(rock) & valid_c
    forest_c = to_cells(masks["forest"]) & valid_c
    roads_c = to_cells(masks["roads"]) & valid_c
    lifts_c = to_cells(masks["lifts"]) & valid_c
    run_cells = [(label, to_cells(mask) & valid_c) for label, mask in masks["runs"].items()]

    layer_names = cfg.get("layers", {})
    run_layer_name = str(layer_names.get("ski_runs", "ski_runs"))

    # Keep all material bodies non-overlapping. Lifts have highest priority, then
    # each run class in stable alphabetical order, followed by roads and forest.
    claimed = lifts_c.copy()
    allocated_runs = []
    for label, cells in run_cells:
        allocated = cells & ~claimed
        allocated_runs.append((label, allocated))
        claimed |= allocated

    cat_roads = roads_c & ~claimed
    claimed |= cat_roads
    cat_forest = forest_c & ~claimed
    claimed |= cat_forest
    cat_rock = rock_c & ~claimed
    claimed |= cat_rock
    cat_snow = valid_c & ~claimed

    model = cfg.get("model", {})
    features = cfg.get("features", {})
    cap = float(model.get("material_cap_depth_mm", 0.8))
    base = float(model.get("base_thickness_mm", 3.0))
    surface_layer_depth = surface_layer_depth_mm(cfg)
    road_height = float(features.get("roads", {}).get("height_mm", 0.4))
    run_height = float(features.get("runs", {}).get("height_mm", 0.2))
    lift_height = float(features.get("lifts", {}).get("height_mm", run_height))
    core_top = np.maximum(grid.z_mm - cap, base * 0.25)
    zero = np.zeros_like(grid.z_mm)
    shell_base = np.maximum(core_top - surface_layer_depth, zero)
    shell_top = np.maximum(core_top, grid.z_mm - surface_layer_depth)

    core = repair_mesh(named_solid("Structural core", valid_c, grid, zero, core_top))
    exposed = repair_mesh(named_solid("Exposed rock", cat_rock, grid, core_top, grid.z_mm))
    snow = repair_mesh(named_solid("Snow", cat_snow, grid, shell_base, shell_top))
    forest = repair_mesh(named_solid("Forest", cat_forest, grid, shell_base, shell_top))
    roads = repair_mesh(named_solid("Roads", cat_roads, grid, shell_base, shell_top + road_height))
    lifts = repair_mesh(named_solid("Lifts", lifts_c, grid, shell_base, shell_top + lift_height))

    layer_display_names = {
        "forest": "forest",
        "road_areas": "road_areas",
        "roads": "roads",
        "ski_runs": run_layer_name,
        "lifts": "lifts",
    }

    structural_parts = [part for part in (core, exposed) if part is not None]
    if not structural_parts:
        raise BuildError("No structural terrain mesh generated")
    structural = trimesh.util.concatenate(structural_parts)
    structural.metadata["name"] = "Structural core and exposed rock"

    parts = [
        (structural, "Structural core and exposed rock"),
        (snow, "Snow"),
        (forest, f"{layer_display_names['forest']}"),
        (roads, f"{layer_display_names['roads']}"),
        (lifts, f"{layer_display_names['lifts']}"),
    ]
    for label, cells in allocated_runs:
        name = f"{run_layer_name} - {label}" if label else run_layer_name
        parts.append((repair_mesh(named_solid(name, cells, grid, core_top, grid.z_mm + run_height)), name))
    return parts


def export_parts(parts, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for mesh, name in parts:
        if mesh is None: continue
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
        mesh.export(output_dir / f"{safe}.stl")
