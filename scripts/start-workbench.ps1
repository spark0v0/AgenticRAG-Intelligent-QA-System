param([ValidateRange(1024, 65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
# Keep this script ASCII-compatible for both Windows PowerShell 5.1 and PowerShell 7.
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create this project''s .venv and install dependencies as described in README first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Build the frontend first: npm --prefix frontend run build' }
Push-Location $projectRoot
try {
    $env:PYTHONUTF8 = '1'
    & $pythonPath -m uvicorn src.api.main:app --host 127.0.0.1 --port $Port --workers 1
} finally { Pop-Location }
