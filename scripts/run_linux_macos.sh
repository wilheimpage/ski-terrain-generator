#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

venv_path="$PWD/.venv"
project_config=""
preview_only=false

if [ $# -gt 0 ]; then
  project_config="$1"
  shift
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --preview-only)
      preview_only=true
      ;;
    --help|-h)
      echo "Usage: $0 [project.yml] [--preview-only]"
      exit 0
      ;;
    *)
      if [ -z "$project_config" ]; then
        project_config="$1"
      else
        echo "Unexpected argument: $1" >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [ ! -d "$venv_path" ]; then
  python3 -m venv "$venv_path"
fi

# shellcheck disable=SC1091
source "$venv_path/bin/activate"

dependencies_healthy=false
if python -m pip show ski-terrain-generator >/dev/null 2>&1; then
  if python -m pip check >/dev/null 2>&1; then
    dependencies_healthy=true
  fi
fi

if [ "$dependencies_healthy" != true ]; then
  python -m pip install --upgrade pip
  if [ -f requirements.txt ]; then
    python -m pip install -r requirements.txt
  fi
  python -m pip install -e .
fi

if [ -z "$project_config" ]; then
  read -r -p "Enter the project YAML path (default: config/projects/example.yml): " project_config
fi

if [ -z "$project_config" ]; then
  project_config="config/projects/example.yml"
fi

cli_args=("$project_config")
if [ "$preview_only" = true ]; then
  cli_args+=(--preview-only)
fi

ski-terrain "${cli_args[@]}"
