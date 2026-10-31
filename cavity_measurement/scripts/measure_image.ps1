param(
    [Alias('ImagePath', 'ImagesPath')][string]$InputPath,
    [string]$MmPerPixel,
    [string]$OutputPath,
<<<<<<< HEAD
    [ValidateSet('inner', 'outer', 'both')][string]$BoundarySide = 'inner'
=======
    [ValidateSet('inner', 'outer', 'both')][string]$BoundarySide = 'both'
>>>>>>> ca0e77ee125e049605093452d1724d6d6f28137f
)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if ([string]::IsNullOrWhiteSpace($InputPath)) {
    $InputPath = Read-Host 'Image or folder path (Enter = default images folder)'
}
$InputPath = $InputPath.Trim().Trim([char[]]@('"', "'")).Trim()
if ([string]::IsNullOrWhiteSpace($InputPath)) {
    $InputPath = Join-Path (Split-Path -Parent $taskRoot) '图片'
}
if (-not (Test-Path -LiteralPath $InputPath)) {
    [Console]::Error.WriteLine("Input path does not exist: $InputPath")
    exit 2
}
$taskInput = Get-Item -LiteralPath $InputPath
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
if ($taskInput.PSIsContainer) {
    Write-Host 'Mode: folder measurement'
    $taskArgs = @('-X', 'utf8', (Join-Path $taskRoot 'tools\measure_folder.py'),
                  '--images', $taskInput.FullName)
} else {
    Write-Host 'Mode: single image measurement'
    $taskArgs = @('-X', 'utf8', (Join-Path $taskRoot 'cavity_measure.py'),
                  'measure', '--image', $taskInput.FullName)
}
Write-Host "Input: $($taskInput.FullName)"
$taskArgs += @('--boundary-side', $BoundarySide)
<<<<<<< HEAD
Write-Host "Boundary mode: $BoundarySide"
=======
Write-Host "Boundary mode: $BoundarySide (inner = A floor candidate; outer = exterior rim)"
>>>>>>> ca0e77ee125e049605093452d1724d6d6f28137f
if (-not [string]::IsNullOrWhiteSpace($MmPerPixel)) {
    $taskArgs += @('--mm-per-pixel', $MmPerPixel.Trim())
    Write-Host "Calibration: explicit scale $($MmPerPixel.Trim()) mm/pixel"
} elseif ($BoundarySide -eq 'outer') {
    Write-Host 'Calibration: outer pixels only (no outer-plane calibration supplied)'
} elseif (Test-Path -LiteralPath (Join-Path $taskRoot 'config\calibration.json')) {
    Write-Host 'Calibration: automatic default (config/calibration.json)'
} else {
    Write-Host 'Calibration: pixels only (no default calibration file)'
}
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) { $taskArgs += @('--out', $OutputPath) }
& $taskPython @taskArgs
exit $LASTEXITCODE
