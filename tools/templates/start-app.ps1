param(
    [string]$PythonPath = "",
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string]$IndexUrl = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
# Use only ASCII in this wrapper so Windows PowerShell 5.1 does not depend on
# a UTF-8 BOM or the system ANSI code page when loading the entry-point script.
$scriptName = (-join ([char[]](0x542f, 0x52a8, 0x6f14, 0x793a))) + ".ps1"
$scriptPath = Join-Path $projectRoot $scriptName
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "The application is incomplete. Extract the entire ZIP before starting it."
}
& $scriptPath @PSBoundParameters
