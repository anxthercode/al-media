Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = & (Join-Path $PSScriptRoot 'version.ps1')
$tree = Join-Path $root 'dist\ALMedia'
if (-not (Test-Path (Join-Path $tree 'ALMedia.exe'))) { throw 'Portable EXE missing' }
foreach ($name in @('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'deno.exe')) {
    $path = Join-Path $tree "tools\$name"
    if (-not (Test-Path -LiteralPath $path)) { throw "Portable tool missing: $name" }
    $flag = if ($name -like 'ff*') { '-version' } else { '--version' }
    $output = & $path $flag 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Tool probe failed: $name" }
    Write-Output ($output | Select-Object -First 1)
}
if (-not (Test-Path (Join-Path $root "dist\ALMedia-$version-portable-win-x64.zip"))) { throw 'Portable ZIP missing' }
if (-not (Test-Path (Join-Path $tree '_runtime_v2\PySide6\QtCore.pyd'))) { throw 'Versioned runtime missing QtCore' }
if (Test-Path (Join-Path $tree '_runtime_v2\icuuc.dll')) { throw 'Incompatible ICU DLL included in runtime' }
$oldQtPlatform = $env:QT_QPA_PLATFORM
$oldPath = $env:PATH
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $app = Start-Process -FilePath (Join-Path $tree 'ALMedia.exe') -ArgumentList '--smoke-gui' -WindowStyle Hidden -PassThru
    if (-not $app.WaitForExit(15000)) {
        Stop-Process -Id $app.Id -Force
        throw 'Packaged GUI did not exit during smoke test'
    }
    if ($app.ExitCode -ne 0) { throw "Packaged GUI failed with exit code $($app.ExitCode)" }
    Write-Host 'Packaged GUI smoke passed.'
} finally {
    $env:QT_QPA_PLATFORM = $oldQtPlatform
    $env:PATH = $oldPath
}
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\local-engine-smoke.py') --tools-root (Join-Path $tree 'tools')
if ($LASTEXITCODE -ne 0) { throw 'Local engine smoke failed' }
Write-Host 'Portable tree smoke checks passed.'
