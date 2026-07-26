from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builder import run_build
from .config import load_layered_config
from .errors import BuildError


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a multi-colour 3MF ski terrain model")
    p.add_argument("project", type=Path, help="Project YAML, e.g. config/projects/craigieburn.yml")
    p.add_argument("--defaults", type=Path, default=Path("config/default.yml"))
    p.add_argument("--printer", type=Path, default=Path("config/printers/bambu-a1-04.yml"))
    p.add_argument("--profile", type=Path, default=Path("config/profiles/display.yml"))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--preview-only", action="store_true", help="Create PNG/report but skip mesh generation")
    mode.add_argument("--validate-only", action="store_true", help="Validate inputs and print resolved settings")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Override any YAML value; repeatable")
    p.add_argument("--vertical-scale", type=float, help="Shortcut for model.vertical_exaggeration")
    p.add_argument("--rock-threshold", type=float, help="Shortcut for rock.score_threshold")
    p.add_argument("--line-width", type=float, help="Shortcut for printer.line_width_mm")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    overrides = list(args.set)
    if args.vertical_scale is not None: overrides.append(f"model.vertical_exaggeration={args.vertical_scale}")
    if args.rock_threshold is not None: overrides.append(f"rock.score_threshold={args.rock_threshold}")
    if args.line_width is not None: overrides.append(f"printer.line_width_mm={args.line_width}")
    try:
        cfg = load_layered_config(args.project, args.defaults, args.printer, args.profile, overrides)
        mode = "validate" if args.validate_only else "preview" if args.preview_only else "full"
        report = run_build(cfg, mode)
        print(json.dumps(report, indent=2))
        return 0
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
