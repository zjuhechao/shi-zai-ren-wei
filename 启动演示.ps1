param(
    [string]$PythonPath = "",
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string]$IndexUrl = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating the local Python environment..." -ForegroundColor Cyan
    $pythonCandidates = @()
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "The supplied PythonPath does not exist. Provide the full path to python.exe."
        }
        $pythonCandidates += [pscustomobject]@{ Command = (Resolve-Path -LiteralPath $PythonPath).Path; Arguments = @() }
    } else {
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            $pythonCandidates += [pscustomobject]@{ Command = $pyLauncher.Source; Arguments = @("-3.12") }
            $pythonCandidates += [pscustomobject]@{ Command = $pyLauncher.Source; Arguments = @("-3") }
        }
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notmatch "\\WindowsApps\\") {
            $pythonCandidates += [pscustomobject]@{ Command = $pythonCommand.Source; Arguments = @() }
        }
    }
    $chosenPython = $null
    foreach ($candidate in $pythonCandidates) {
        try {
            $probeArguments = @($candidate.Arguments)
            $probeOutput = & $candidate.Command @probeArguments -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
            $probeExitCode = $LASTEXITCODE
            $probeVersion = (@($probeOutput) -join "").Trim()
            if ($probeExitCode -eq 0 -and $probeVersion -match '^\d+\.\d+$' -and [version]$probeVersion -ge [version]"3.11") {
                $chosenPython = $candidate
                break
            }
        } catch {
            # A launcher may exist even when no compatible Python is registered.
            continue
        }
    }
    if (-not $chosenPython) {
        throw "No compatible Python was found. Install Python 3.12, or run this script with -PythonPath followed by the full path to python.exe."
    }
    $bootstrapArguments = @($chosenPython.Arguments)
    & $chosenPython.Command @bootstrapArguments -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python environment." }
}

$pythonVersion = & $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.11") {
    throw "Python 3.11 or newer is required; Python 3.12 is recommended for this demo."
}

$requirements = Join-Path $projectRoot "backend\requirements.txt"
$windowsLock = Join-Path $projectRoot "backend\requirements-lock.windows-py312.txt"
if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT -and
    [version]$pythonVersion -eq [version]"3.12" -and (Test-Path -LiteralPath $windowsLock)) {
    $requirements = $windowsLock
}
$selectedIndex = if ($IndexUrl) { $IndexUrl.Trim().TrimEnd("/") } else { "https://pypi.org/simple" }
$indexUri = $null
if (-not [uri]::TryCreate($selectedIndex, [System.UriKind]::Absolute, [ref]$indexUri) -or
    $indexUri.Scheme -ne "https" -or $indexUri.UserInfo -or $indexUri.Query -or $indexUri.Fragment) {
    throw "IndexUrl must be an HTTPS package index without credentials, query, or fragment."
}
$installMarker = Join-Path $projectRoot ".venv\requirements.sha256"
$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $installMarker) { (Get-Content -LiteralPath $installMarker -Raw).Trim() } else { "" }
$dependencyCheck = Join-Path $projectRoot "backend\scripts\check_dependencies.py"
if (-not (Test-Path -LiteralPath $dependencyCheck -PathType Leaf)) {
    throw "The offline dependency checker is missing. Extract the complete application or repository."
}
$dependenciesReady = $false
if ($installedHash -eq $requirementsHash) {
    & $venvPython $dependencyCheck --requirements $requirements *> $null
    $dependenciesReady = $LASTEXITCODE -eq 0
    if (-not $dependenciesReady) {
        Write-Host "The install marker exists, but dependencies are missing, changed or cannot be imported. Repairing them..." -ForegroundColor Yellow
    }
}
if (-not $dependenciesReady) {
    Write-Host "Installing project dependencies. Internet access is required for the first run..." -ForegroundColor Cyan
    Write-Host ("Dependency file: " + (Split-Path -Leaf $requirements) + "; one-time index: " + $selectedIndex) -ForegroundColor DarkGray
    try {
        & $venvPython -m pip --disable-pip-version-check install -r $requirements --index-url $selectedIndex --timeout 30 --retries 1
        if ($LASTEXITCODE -ne 0) { throw "pip installation failed." }
    } catch {
        throw "Dependency installation failed. If PyPI is unreachable, retry with -IndexUrl https://mirrors.zju.edu.cn/pypi/web/simple. No persistent pip settings were changed."
    }
    & $venvPython $dependencyCheck --requirements $requirements *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency validation failed after installation. No success marker was written. Check your Python version and the pinned requirements file."
    }
    Set-Content -LiteralPath $installMarker -Value $requirementsHash -Encoding ASCII
}

$envFile = Join-Path $projectRoot "backend\.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath "backend\.env.example" -Destination $envFile
    Write-Host "Created backend\.env. Local calculations are available; configure NEW API keys for AI and RAG." -ForegroundColor Yellow
}

if ($Port -gt 0) { $env:APP_PORT = [string]$Port }
try {
    $runtimeJson = & $venvPython -c "import json,sys; sys.path.insert(0,'backend'); from app.config import get_settings; s=get_settings(); print(json.dumps({'host':s.app_host,'port':s.app_port,'api_configured':s.api_configured,'embeddings_configured':s.embeddings_configured}))" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Invalid runtime settings." }
} catch {
    throw "Unable to read runtime settings. Check backend/.env without sharing its private values."
}
$runtimeSettings = $runtimeJson | ConvertFrom-Json
$runtimePort = [int]$runtimeSettings.port
if ($runtimePort -lt 1 -or $runtimePort -gt 65535) { throw "APP_PORT must be between 1 and 65535." }
if (-not $runtimeSettings.host) { throw "APP_HOST is empty. Set it to 127.0.0.1 for a local demo." }
$hostAddress = $null
if ($runtimeSettings.host -ne "localhost" -and
    -not [System.Net.IPAddress]::TryParse([string]$runtimeSettings.host, [ref]$hostAddress)) {
    throw "APP_HOST must be an IP address or localhost, not a URL. Use 127.0.0.1 for the local demo."
}
if ($runtimeSettings.host -ne "localhost" -and -not [System.Net.IPAddress]::IsLoopback($hostAddress)) {
    throw "This Windows demo only starts on a loopback address. Set APP_HOST=127.0.0.1 or ::1. It has no public-service authentication."
}
Write-Host ("Configuration presence only: LLM=" + [bool]$runtimeSettings.api_configured + "; embedding=" + [bool]$runtimeSettings.embeddings_configured + ". This is not an online connectivity or RAG check.") -ForegroundColor DarkGray
if (-not $runtimeSettings.api_configured -or -not $runtimeSettings.embeddings_configured) {
    Write-Host "AI/RAG configuration is incomplete. Local calculations and the fixed demonstration PDF remain available." -ForegroundColor Yellow
}
$browserHost = if ($runtimeSettings.host -in @("0.0.0.0", "::", "localhost")) { "127.0.0.1" } else { [string]$runtimeSettings.host }
$displayHost = if ($browserHost.Contains(":")) { "[" + $browserHost + "]" } else { $browserHost }
$browserUrl = "http://" + $displayHost + ":" + $runtimePort
$alternativePort = if ($runtimePort -eq 18061) { 18062 } else { 18061 }
try {
    $existingService = Invoke-RestMethod -Uri ($browserUrl + "/api/health") -TimeoutSec 3 -ErrorAction Stop
    if ($existingService.status -eq "ok" -and $existingService.calculation_engine -eq "python") {
        Write-Host ("An existing demo is already running at " + $browserUrl + " (version " + $existingService.version + ").") -ForegroundColor Yellow
        Write-Host ("Use that page, or choose another free port (for example -Port " + $alternativePort + "). The existing process was not changed.") -ForegroundColor Yellow
        exit 0
    }
} catch {
    # No compatible HTTP service was found; check whether its listening port is occupied.
}
$portInUse = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $runtimePort }
if ($portInUse) {
    throw ("Port " + $runtimePort + " is already in use. Choose another free port (for example -Port " + $alternativePort + "); no existing service will be stopped.")
}

Write-Host ("Open " + $browserUrl + " in your browser.") -ForegroundColor Green
Write-Host "Close this window to stop the server." -ForegroundColor DarkGray
& $venvPython backend\run.py
if ($LASTEXITCODE -ne 0) { throw "The server stopped with an error. Check the message above." }
