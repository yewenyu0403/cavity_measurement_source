param([string]$ImagesPath, [string]$MmPerPixel, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ImagesPath)) {
    $ImagesPath = Join-Path (Split-Path -Parent $taskRoot) '图片'
}
# Use the shared default calibration unless an explicit scale is supplied.
$taskParameters = @{ InputPath = $ImagesPath; MmPerPixel = $MmPerPixel }
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) { $taskParameters.OutputPath = $OutputPath }
& (Join-Path $PSScriptRoot 'measure_image.ps1') @taskParameters
exit $LASTEXITCODE
