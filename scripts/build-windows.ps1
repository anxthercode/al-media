param([switch]$Incremental)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = & (Join-Path $PSScriptRoot 'version.ps1')
Push-Location $root
try {
    if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw 'Run scripts/bootstrap.ps1 first' }
    & .\.venv\Scripts\python.exe scripts\make-icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    foreach ($name in @('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'deno.exe')) {
        if (-not (Test-Path (Join-Path 'tools' $name))) { throw "Run scripts/fetch-tools.ps1 first: $name missing" }
    }
    $packagerArgs = @('-m', 'PyInstaller', '--noconfirm', 'packaging\ALMedia.spec')
    if (-not $Incremental) { $packagerArgs += '--clean' }
    & .\.venv\Scripts\python.exe @packagerArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $tree = Join-Path $root 'dist\ALMedia'
    $runtime = Join-Path $tree '_runtime_v2'
    if (-not (Test-Path -LiteralPath $runtime)) { throw 'Packaged runtime missing' }
    $allowedTree = [IO.Path]::GetFullPath((Join-Path $root 'dist\ALMedia')) + [IO.Path]::DirectorySeparatorChar
    foreach ($candidate in @($runtime, (Join-Path $runtime 'tools'), (Join-Path $runtime 'assets'), (Join-Path $tree 'tools'), (Join-Path $tree 'assets'))) {
        if (-not [IO.Path]::GetFullPath($candidate).StartsWith($allowedTree, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build path escaped output directory' }
    }
    $internalTools = Join-Path $runtime 'tools'
    if (Test-Path -LiteralPath $internalTools) {
        Move-Item -LiteralPath $internalTools -Destination (Join-Path $tree 'tools')
    }
    $internalAssets = Join-Path $runtime 'assets'
    if (Test-Path -LiteralPath $internalAssets) {
        Move-Item -LiteralPath $internalAssets -Destination (Join-Path $tree 'assets')
    }
    foreach ($name in @('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'deno.exe')) {
        if (-not (Test-Path (Join-Path $tree "tools\$name"))) { throw "Package missing $name" }
    }
    Copy-Item -LiteralPath (Join-Path $root 'docs\USER_GUIDE.md') -Destination (Join-Path $tree 'README.md') -Force
    foreach ($notice in @('LICENSE', 'THIRD_PARTY_NOTICES.md')) {
        Copy-Item -LiteralPath (Join-Path $root $notice) -Destination (Join-Path $tree $notice) -Force
    }
    $zip = Join-Path $root "dist\ALMedia-$version-portable-win-x64.zip"
    if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -LiteralPath $tree -DestinationPath $zip
} finally { Pop-Location }
