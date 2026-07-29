# Ski Terrain Generator

A reusable Python project that converts a cropped LiDAR DEM (`.tif`) plus manually digitised QGIS layers in a GeoPackage (`.gpkg`) into a printer-aware, multi-part `.3mf` terrain model.

The optional QGIS project (`.qgz`) is inspected for reporting only. Geometry comes from the saved TIFF and GeoPackage, so unsaved QGIS edits are not included.

**N.B: This project was designed around New Zealad 1m LiDAR DEM data, using the NZTM2000 coordinate reference system (CRS). I have not tested this using any other CRS, but theoretically you should be able to use a GeoTIFF in any CRS, as long as your gpkg layers are using the same CRS, without any modification to the scripts.**

**If you try this and it works, let me know!**

## Repository layout

```text
config/default.yml              shared geometry and rock settings
config/printers/*.yml           nozzle and extrusion-width settings
config/profiles/*.yml           display, realistic, exaggerated styles
config/projects/*.yml           one file per ski area
src/ski_terrain/                generator source code
input/                          local GIS inputs; ignored by Git
output/                         generated previews and models; ignored by Git
```

## Installation

Use 64-bit Python 3.11 or 3.12.

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

Linux/macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## Basic workflow

The recommended entry point is the wrapper script, which creates/uses the local virtual environment, installs dependencies if needed, and runs the generator for you.

### Simple GeoTIFF to mesh conversion

For a bare-bones conversion with no colour or configuration, use the simple converter:

```powershell
py -3 -m ski_terrain.simple_convert input/BX20.tif --output output/simple_mesh.obj --max-dimension 180
```

Use `--format stl` to write an STL instead of OBJ.


1. Copy the cropped DEM, GeoPackage, and optional QGZ into `input/`.
2. Copy `config/projects/example.yml` to a ski-area-specific name.
3. Set its input filenames and output stem.
4. Generate a quick classification preview from PowerShell:

```powershell
.\scripts\run_windows.ps1 -ProjectConfig config/projects/example.yml -PreviewOnly
```

On Linux/macOS, use:

```bash
./scripts/run_linux_macos.sh config/projects/example.yml --preview-only
```

5. Adjust YAML values until the preview looks right.
6. Generate the final 3MF and STL parts:

```powershell
.\scripts\run_windows.ps1 -ProjectConfig config/projects/example.yml
```

If you omit the project path, the scripts prompt for it and fall back to `config/projects/example.yml`.

## Configuration precedence

Configuration is merged in this order, with later values winning:

1. `config/default.yml`
2. printer file
3. profile file
4. project file
5. command-line overrides

The default command therefore means:

```powershell
ski-terrain config/projects/example.yml `
  --defaults config/default.yml `
  --printer config/printers/bambu-a1-04.yml `
  --profile config/profiles/display.yml
```

## Printer-aware feature widths

Widths are normally specified as extrusion counts rather than hard-coded millimetres:

```yaml
printer:
  line_width_mm: 0.42
features:
  roads: {extrusions: 2}
  runs: {extrusions: 1}
  lifts: {extrusions: 1}
```

This produces 0.84 mm roads and 0.42 mm runs/lifts. Switching to the supplied 0.6 mm printer profile automatically produces 1.24 mm roads and 0.62 mm runs/lifts.

A project can force an exact width when required:

```yaml
features:
  roads:
    width_mm: 0.90
```

`width_mm` takes precedence over `extrusions`.

## Main parameters

Vertical scale and model dimensions:

```yaml
model:
  maximum_dimension_mm: 250
  base_thickness_mm: 3
  vertical_exaggeration: 1.0
  grid_spacing_mm: 0.42
  material_cap_depth_mm: 0.8
```

Rock classification:

```yaml
rock:
  score_threshold: 0.65
  slope_center_degrees: 42.75
  slope_span_degrees: 13.25
  roughness_weight: 0.575
  minimum_patch_area_mm2: 1.5
```

- Lower `score_threshold` gives more rock.
- Higher `score_threshold` gives less rock.
- Higher `minimum_patch_area_mm2` removes more isolated speckles.
- `grid_spacing_mm` controls output detail and memory use; halving it creates roughly four times as many cells.

Feature heights:

```yaml
features:
  roads: {height_mm: 0.40}
  runs: {height_mm: 0.20}
  lifts: {height_mm: 0.20}
```

## Command-line overrides

Use YAML for repeatable settings. Command-line overrides are useful for experiments and do not edit any file.

```powershell
ski-terrain config/projects/example.yml --preview-only --rock-threshold 0.62
ski-terrain config/projects/example.yml --vertical-scale 1.3
ski-terrain config/projects/example.yml --line-width 0.45
```

Any setting can be overridden using dotted `key=value` syntax:

```powershell
ski-terrain config/projects/example.yml --preview-only `
  --set rock.minimum_patch_area_mm2=1.0 `
  --set features.roads.extrusions=2.5 `
  --set output.diagnostic_previews=true
```

## Profiles

Choose another supplied profile:

```powershell
ski-terrain config/projects/example.yml --profile config/profiles/realistic.yml --preview-only
```

Profiles are ordinary YAML overlays. Add your own without changing Python code.

## Validation

```powershell
ski-terrain config/projects/example.yml --validate-only
```

This checks paths, CRS, layer/field names, resolved widths, dimensions, feature counts, and rock coverage without building meshes.

## Expected GeoPackage layers

| Layer | Geometry | Purpose |
|---|---|---|
| `forest` | polygon | green forest areas |
| `road_areas` | polygon | car parks and broad road surfaces |
| `roads` | line | roads and lift/tow centre lines |
| `ski_runs` | line | run centre lines; every distinct difficulty value becomes a separate object |

Default fields are `roads.name` and `ski_runs.difficulty`. Override layer and field names in YAML.

### Dynamic run objects

The generator does not contain a fixed list of run difficulties. It reads every distinct value from the configured ski-run difficulty field and creates a separate 3MF/STL object for each one. For example, values of `Green`, `Blue`, `Red`, `Black`, `Ski Route`, and `Terrain Park` produce six independently assignable objects. New values require no Python or YAML changes.

Matching is based on the complete field value after trimming surrounding whitespace. Capitalisation is preserved in the object name. Null, empty, or whitespace-only values are grouped into `Run - Unclassified`; change that label with:

```yaml
features:
  run_difficulty_field: difficulty
  blank_difficulty_label: Unclassified
```


## Outputs

- `<stem>_preview.png`
- `<stem>_report.json`
- `<stem>.3mf`
- `<stem>_parts/*.stl`

The 3MF contains separate assignable parts for the structural core/rock, snow, forest, roads, lifts, and one additional object for every distinct ski-run difficulty value. Filament colours are assigned in the slicer.
