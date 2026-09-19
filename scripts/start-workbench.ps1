param([ValidateRange(1024, 65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先按 README 创建当前项目自己的 .venv 并安装依赖。' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw '请先在 frontend 运行 npm run build。' }
Push-Location $projectRoot
try {
    $env:PYTHONUTF8 = '1'
    & $pythonPath -m uvicorn src.api.main:app --host 127.0.0.1 --port $Port --workers 1
} finally { Pop-Location }
