param(
    [Alias('ImagePath', 'ImagesPath')][string]$InputPath,
    [string]$MmPerPixel,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
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
if (-not $PSBoundParameters.ContainsKey('MmPerPixel')) {
    $MmPerPixel = Read-Host 'Known calibrated mm/pixel (Enter = pixels only)'
}
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
if (-not [string]::IsNullOrWhiteSpace($MmPerPixel)) { $taskArgs += @('--mm-per-pixel', $MmPerPixel.Trim()) }
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) { $taskArgs += @('--out', $OutputPath) }
& $taskPython @taskArgs
exit $LASTEXITCODE
