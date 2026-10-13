param(
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$Prepare,
    [switch]$OpenBrowser,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$indexPath = Join-Path $projectRoot 'frontend\dist\index.html'
$url = "http://127.0.0.1:$Port/chat"
$browserJob = $null
# Keep this script ASCII-compatible for both Windows PowerShell 5.1 and PowerShell 7.
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Python environment missing. Follow README: python -m venv .venv; then install requirements.txt with requirements-verified.txt constraints.'
    }
    if ($Prepare) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            throw 'Node.js/npm not found. Install Node.js 24.15+ and reopen this launcher.'
        }
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules\.package-lock.json'))) {
            Write-Host '[1/3] Installing frontend dependencies from the lockfile...'
            & npm.cmd --prefix frontend ci
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Check the npm output above.' }
        }
        Write-Host '[2/3] Building frontend...'
        & npm.cmd --prefix frontend run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. The server has not been started.' }
    }
    if (-not (Test-Path -LiteralPath $indexPath)) {
        throw 'Build the frontend first: npm --prefix frontend run build (or double-click start.bat).'
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listener) {
        # Compare the static entry with this checkout before opening an occupied port.
        # Do not terminate any existing process or select a different port silently.
        $sameWorkbench = $false
        try {
            $page = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            $expected = [System.IO.File]::ReadAllText($indexPath)
            $sameWorkbench = $page.StatusCode -eq 200 -and $page.Content.Trim() -eq $expected.Trim()
        } catch { $sameWorkbench = $false }
        if (-not $sameWorkbench) {
            throw "Port $Port is occupied by another service or build. Stop it yourself, or use start.bat -Port 8001."
        }
        Write-Host "Workbench is already running: $url"
        Write-Host 'The current frontend build is ready. Backend code changes require restarting the existing server.'
        if ($OpenBrowser -and -not $NoBrowser) { Start-Process $url }
        return
    }
    Write-Host "[3/3] Starting workbench: $url"
    Write-Host 'Keep this window open. Press Ctrl+C to stop the server.'
    if ($OpenBrowser -and -not $NoBrowser) {
        # A short-lived job waits for readiness while Uvicorn owns this console.
        $browserJob = Start-Job -ArgumentList $url -ScriptBlock {
            param($Address)
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                try {
                    $response = Invoke-WebRequest -Uri $Address -UseBasicParsing -TimeoutSec 2
                    if ($response.StatusCode -eq 200 -and $response.Content.Contains('AgenticRAG')) {
                        Start-Process $Address
                        return
                    }
                } catch { }
                Start-Sleep -Milliseconds 500
            }
        }
    }
    $env:PYTHONUTF8 = '1'
    & $pythonPath -m uvicorn src.api.main:app --host 127.0.0.1 --port $Port --workers 1
    if ($LASTEXITCODE -ne 0) { throw "Server exited with code $LASTEXITCODE. See the output above." }
} finally {
    if ($null -ne $browserJob) {
        Stop-Job -Job $browserJob -ErrorAction SilentlyContinue
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
