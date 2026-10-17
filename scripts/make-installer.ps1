Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = & (Join-Path $PSScriptRoot 'version.ps1')
$binary = Join-Path $root 'dist\ALMedia\ALMedia.exe'
if (-not (Test-Path -LiteralPath $binary)) { throw 'Run scripts/build-windows.ps1 first' }
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidates = @((Join-Path $root 'build\InnoSetup\ISCC.exe'), 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { $iscc = $candidate; break }
    }
    if (-not $iscc) { throw 'Install Inno Setup 6, or put ISCC.exe on PATH' }
}
& $iscc "/DMyAppVersion=$version" (Join-Path $root 'packaging\installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }

$releaseFiles = @("ALMedia-$version-Setup-win-x64.exe", "ALMedia-$version-portable-win-x64.zip")
$sums = foreach ($name in $releaseFiles) {
    $artifact = Join-Path $root "dist\$name"
    if (-not (Test-Path -LiteralPath $artifact)) { throw "Release artifact missing: $name" }
    "{0}  {1}" -f (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant(), $name
}
$sums | Set-Content -LiteralPath (Join-Path $root 'dist\SHA256SUMS.txt') -Encoding ascii
