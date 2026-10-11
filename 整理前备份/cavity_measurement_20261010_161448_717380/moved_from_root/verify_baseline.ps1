param([string]$ImagesPath, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
$taskArgs = @('-X', 'utf8', (Join-Path $PSScriptRoot 'verify_baseline.py'))
if (-not [string]::IsNullOrWhiteSpace($ImagesPath)) { $taskArgs += @('--images', $ImagesPath) }
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) { $taskArgs += @('--out', $OutputPath) }
& $taskPython @taskArgs
exit $LASTEXITCODE
