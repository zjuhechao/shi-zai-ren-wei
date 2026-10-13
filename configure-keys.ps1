param([string]$PythonPath = "")

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$script = Join-Path $projectRoot "backend\scripts\configure_secrets.py"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "The configuration helper is missing. Extract or clone the complete repository first."
}
$candidates = @()
if ($PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "PythonPath must be the full path to an installed python.exe. Do not pass keys as command arguments."
    }
    $candidates += [pscustomobject]@{ Command = (Resolve-Path -LiteralPath $PythonPath).Path; Arguments = @() }
} else {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $candidates += [pscustomobject]@{ Command = $venvPython; Arguments = @() }
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidates += [pscustomobject]@{ Command = $launcher.Source; Arguments = @("-3.12") }
        $candidates += [pscustomobject]@{ Command = $launcher.Source; Arguments = @("-3") }
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notmatch "\\WindowsApps\\") {
        $candidates += [pscustomobject]@{ Command = $pythonCommand.Source; Arguments = @() }
    }
}
$selected = $null
foreach ($candidate in $candidates) {
    try {
        $arguments = @($candidate.Arguments)
        $probe = & $candidate.Command @arguments -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
        $code = $LASTEXITCODE
        $version = (@($probe) -join "").Trim()
        if ($code -eq 0 -and $version -match '^\d+\.\d+$' -and [version]$version -ge [version]"3.11") {
            $selected = $candidate
            break
        }
    } catch { continue }
}
if (-not $selected) {
    throw "No usable Python was found. Install Python 3.12 and select Add python.exe to PATH, or use -PythonPath with the full path to python.exe. This helper does not need project dependencies or API access."
}
Write-Host "Configure keys in your own terminal only. Never add keys to commands, screenshots or Git." -ForegroundColor Yellow
$arguments = @($selected.Arguments)
& $selected.Command @arguments $script
if ($LASTEXITCODE -ne 0) { throw "Configuration was not saved. Review the message above and try again." }
