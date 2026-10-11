param([string]$ImagePath, [string]$MmPerPixel)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if ([string]::IsNullOrWhiteSpace($ImagePath)) {
    $ImagePath = (Read-Host 'Image path (or drag an image onto measure_image.cmd)').Trim('"')
}
if (-not (Test-Path -LiteralPath $ImagePath -PathType Leaf)) {
    Write-Error 'Image does not exist.'
    exit 2
}
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
if (-not $PSBoundParameters.ContainsKey('MmPerPixel')) {
    $MmPerPixel = Read-Host 'Known calibrated mm/pixel (Enter = skip; do not enter an example value)'
}
$taskArgs = @('-X','utf8', (Join-Path $taskRoot 'cavity_measure.py'), 'measure',
              '--image', $ImagePath)
if (-not [string]::IsNullOrWhiteSpace($MmPerPixel)) { $taskArgs += @('--mm-per-pixel',$MmPerPixel.Trim()) }
& $taskPython @taskArgs
$taskExit = $LASTEXITCODE
exit $taskExit
