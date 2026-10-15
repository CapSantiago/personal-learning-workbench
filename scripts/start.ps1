param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$plwProject = Split-Path -Parent $PSScriptRoot
$plwPython = Join-Path $plwProject '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $plwPython -PathType Leaf)) {
    throw 'PLW .venv is missing. Follow README.md to prepare the dedicated environment.'
}
Push-Location -LiteralPath $plwProject
try {
    & $plwPython -X utf8 -B (Join-Path $PSScriptRoot 'launch.py') --port $Port
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
