param([string]$ImagePath, [string]$MmPerPixel)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
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
    $MmPerPixel = Read-Host 'Known mm/pixel scale (example 0.02; Enter = pixels only)'
}
$taskStamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$taskOutput = Join-Path $PSScriptRoot (Join-Path 'outputs' $taskStamp)
$taskArgs = @('-X','utf8', (Join-Path $PSScriptRoot 'cavity_measure.py'), 'measure',
              '--image', $ImagePath, '--out', $taskOutput)
if (-not [string]::IsNullOrWhiteSpace($MmPerPixel)) { $taskArgs += @('--mm-per-pixel',$MmPerPixel.Trim()) }
& $taskPython @taskArgs
$taskExit = $LASTEXITCODE
Write-Host ('Results: '+$taskOutput)
exit $taskExit
