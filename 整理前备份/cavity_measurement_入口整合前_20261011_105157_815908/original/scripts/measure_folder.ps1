param([string]$ImagesPath, [string]$MmPerPixel)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
$taskArgs = @('-X', 'utf8', (Join-Path $taskRoot 'tools\measure_folder.py'))
if (-not [string]::IsNullOrWhiteSpace($ImagesPath)) { $taskArgs += @('--images', $ImagesPath.Trim('"')) }
if (-not [string]::IsNullOrWhiteSpace($MmPerPixel)) { $taskArgs += @('--mm-per-pixel', $MmPerPixel.Trim()) }
& $taskPython @taskArgs
exit $LASTEXITCODE
