from __future__ import annotations

import copy
from pathlib import Path
from typing import Any
import yaml

from .errors import BuildError


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BuildError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise BuildError(f"Configuration must be a YAML mapping: {path}")
    return data


def deep_merge(base: dict, overlay: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def parse_scalar(value: str) -> Any:
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise BuildError(f"Invalid override value {value!r}: {exc}") from exc


def set_dotted(config: dict, dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    if not all(parts):
        raise BuildError(f"Invalid configuration key: {dotted_key!r}")
    target = config
    for part in parts[:-1]:
        current = target.get(part)
        if current is None:
            current = {}
            target[part] = current
        if not isinstance(current, dict):
            raise BuildError(f"Cannot set {dotted_key}: {part} is not a mapping")
        target = current
    target[parts[-1]] = value


def resolve_relative_paths(config: dict, project_file: Path) -> dict:
    config = copy.deepcopy(config)
    root = project_file.parent.resolve()
    for section, keys in {
        "inputs": ("dem", "gpkg", "qgz"),
        "output": ("directory",),
    }.items():
        values = config.get(section, {})
        for key in keys:
            raw = values.get(key)
            if not raw:
                continue
            path = Path(str(raw)).expanduser()
            values[key] = str(path if path.is_absolute() else (root / path).resolve())
    return config


def load_layered_config(
    project_path: Path,
    defaults_path: Path | None = None,
    printer_path: Path | None = None,
    profile_path: Path | None = None,
    overrides: list[str] | None = None,
) -> dict:
    cfg: dict = {}
    for path in (defaults_path, printer_path, profile_path, project_path):
        if path is not None:
            cfg = deep_merge(cfg, load_yaml(path.resolve()))
    for expression in overrides or []:
        if "=" not in expression:
            raise BuildError(f"Override must use key=value syntax: {expression}")
        key, raw = expression.split("=", 1)
        set_dotted(cfg, key.strip(), parse_scalar(raw.strip()))
    return resolve_relative_paths(cfg, project_path.resolve())


def feature_width_mm(cfg: dict, feature: str) -> float:
    feature_cfg = cfg.get("features", {}).get(feature, {})
    if "width_mm" in feature_cfg:
        return float(feature_cfg["width_mm"])
    line_width = float(cfg.get("printer", {}).get("line_width_mm", 0.42))
    extrusions = float(feature_cfg.get("extrusions", 1))
    return line_width * extrusions
