# Run from a downloaded ZIP or a Git checkout. No administrator rights needed.
[CmdletBinding()]
param([switch]$UpdateSkills)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'KOMPAS-3D MCP requires Windows.'
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv: winget install --id astral-sh.uv --exact . Then reopen PowerShell and retry.'
}

Push-Location $PSScriptRoot
try {
    & uv sync --locked --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    $installerArgs = @('run', '--locked', 'python', 'scripts/install.py')
    if ($UpdateSkills) { $installerArgs += '--update-skills' }
    & uv @installerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Codex registration failed. See the message above.' }
} finally {
    Pop-Location
}
