$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating the local Python environment..." -ForegroundColor Cyan
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv .venv
    } else {
        throw "Python 3.11 or newer is required. Install Python from python.org, then run again."
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python environment." }
}

$pythonVersion = & $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.11") {
    throw "Python 3.11 or newer is required; Python 3.12 is recommended for this demo."
}

$requirements = Join-Path $projectRoot "backend\requirements.txt"
$installMarker = Join-Path $projectRoot ".venv\requirements.sha256"
$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $installMarker) { (Get-Content -LiteralPath $installMarker -Raw).Trim() } else { "" }
if ($installedHash -ne $requirementsHash) {
    Write-Host "Installing project dependencies. Internet access is required for the first run..." -ForegroundColor Cyan
    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Keep this window open and check the error above." }
    Set-Content -LiteralPath $installMarker -Value $requirementsHash -Encoding ASCII
}

$envFile = Join-Path $projectRoot "backend\.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath "backend\.env.example" -Destination $envFile
    Write-Host "Created backend\.env. Local calculations are available; configure NEW API keys for AI and RAG." -ForegroundColor Yellow
}

Write-Host "Open http://127.0.0.1:8000 in your browser." -ForegroundColor Green
Write-Host "Close this window to stop the server." -ForegroundColor DarkGray
& $venvPython backend\run.py
if ($LASTEXITCODE -ne 0) { throw "The server stopped with an error. Check the message above." }
