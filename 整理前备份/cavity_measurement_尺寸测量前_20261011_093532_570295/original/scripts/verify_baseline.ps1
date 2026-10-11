param([string]$ImagesPath, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
$taskArgs = @('-X', 'utf8', (Join-Path $taskRoot 'tools\verify_baseline.py'))
if (-not [string]::IsNullOrWhiteSpace($ImagesPath)) { $taskArgs += @('--images', $ImagesPath) }
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) { $taskArgs += @('--out', $OutputPath) }
& $taskPython @taskArgs
exit $LASTEXITCODE
