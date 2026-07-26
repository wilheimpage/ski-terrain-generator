from pathlib import Path

from ski_terrain.config import deep_merge, feature_width_mm, load_layered_config, set_dotted


def test_deep_merge_and_width():
    cfg = deep_merge({"printer":{"line_width_mm":0.42},"features":{"roads":{"extrusions":2}}}, {})
    assert feature_width_mm(cfg, "roads") == 0.84


def test_dotted_override():
    cfg = {}
    set_dotted(cfg, "rock.score_threshold", 0.7)
    assert cfg["rock"]["score_threshold"] == 0.7


def test_relative_paths_are_resolved_from_current_working_directory(tmp_path, monkeypatch):
    project_dir = tmp_path / "config" / "projects"
    project_dir.mkdir(parents=True)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "BX20.tif").write_text("dummy", encoding="utf-8")

    project_path = project_dir / "mount-hutt.yml"
    project_path.write_text("inputs:\n  dem: ./input/BX20.tif\n  gpkg: ./input/mount-hutt.gpkg\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cfg = load_layered_config(project_path)

    assert cfg["inputs"]["dem"] == str((input_dir / "BX20.tif").resolve())
    assert cfg["inputs"]["gpkg"] == str((input_dir / "mount-hutt.gpkg").resolve())


def test_project_layers_override_defaults(tmp_path):
    defaults_path = tmp_path / "default.yml"
    defaults_path.write_text("layers:\n  ski_runs: ski_runs\n  road_areas: road_areas\n", encoding="utf-8")

    project_path = tmp_path / "project.yml"
    project_path.write_text("layers:\n  ski_runs: ski-runs\n  road_areas: road-areas\n", encoding="utf-8")

    cfg = load_layered_config(project_path, defaults_path=defaults_path)

    assert cfg["layers"]["ski_runs"] == "ski-runs"
    assert cfg["layers"]["road_areas"] == "road-areas"
