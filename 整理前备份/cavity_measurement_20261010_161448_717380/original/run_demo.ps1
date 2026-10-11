param([switch]$OpenPreview)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
$taskText = & $taskPython -X utf8 (Join-Path $PSScriptRoot 'cavity_measure.py') demo
$taskExit = $LASTEXITCODE
$taskText | Write-Host
if ($taskExit -eq 0 -and $OpenPreview) {
    $taskData = $taskText | ConvertFrom-Json
    Invoke-Item -LiteralPath (Join-Path $taskData.output 'overlay.png')
}
exit $taskExit
