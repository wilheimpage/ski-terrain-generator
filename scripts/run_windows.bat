@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
ski-terrain config\projects\example.yml --preview-only
pause
