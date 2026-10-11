param([switch]$OpenPreview)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
$taskText = & $taskPython -X utf8 (Join-Path $taskRoot 'cavity_measure.py') demo
$taskExit = $LASTEXITCODE
$taskText | Write-Host
if ($taskExit -eq 0 -and $OpenPreview) {
    $taskData = $taskText | ConvertFrom-Json
    Invoke-Item -LiteralPath (Join-Path $taskData.output 'overlay.png')
}
exit $taskExit
