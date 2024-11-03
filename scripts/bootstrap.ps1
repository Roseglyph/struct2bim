$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $ProjectRoot ".tools\uv\uv.exe"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Uv)) {
    throw "Portable uv was not found at $Uv"
}

$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot ".tools\python"
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".cache\uv"

if (-not (Test-Path $VenvPython)) {
    & $Uv python install 3.11
    & $Uv venv --python 3.11 (Join-Path $ProjectRoot ".venv")
}

& $Uv sync --frozen --extra dev
& $VenvPython (Join-Path $ProjectRoot "scripts\verify_environment.py")
