Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -Raw (Join-Path $root 'tools\dependencies.json') | ConvertFrom-Json
$target = Join-Path $root 'tools'
$cache = Join-Path $root 'build\downloads'
New-Item -ItemType Directory -Force $cache | Out-Null
function Get-Verified($entry, [string]$name) {
    $file = Join-Path $cache $name
    if (-not (Test-Path -LiteralPath $file)) { Invoke-WebRequest -Uri $entry.url -OutFile $file -UseBasicParsing }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    if ($hash -ne $entry.sha256.ToLowerInvariant()) { throw "SHA-256 mismatch: $name" }
    return $file
}
$yt = Get-Verified $manifest.'yt-dlp' 'yt-dlp.exe'
Copy-Item -LiteralPath $yt -Destination (Join-Path $target 'yt-dlp.exe') -Force
$deno = Get-Verified $manifest.deno 'deno.zip'
$ffmpeg = Get-Verified $manifest.ffmpeg 'ffmpeg.zip'
$denoDir = Join-Path $cache 'deno'
$ffmpegDir = Join-Path $cache 'ffmpeg'
New-Item -ItemType Directory -Force $denoDir, $ffmpegDir | Out-Null
Expand-Archive -LiteralPath $deno -DestinationPath $denoDir -Force
Expand-Archive -LiteralPath $ffmpeg -DestinationPath $ffmpegDir -Force
$denoExe = Get-ChildItem -LiteralPath $denoDir -Recurse -Filter deno.exe | Select-Object -First 1
if (-not $denoExe) { throw 'Deno archive has no deno.exe' }
Copy-Item -LiteralPath $denoExe.FullName -Destination (Join-Path $target 'deno.exe') -Force
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
    $binary = Get-ChildItem -LiteralPath $ffmpegDir -Recurse -Filter $name | Select-Object -First 1
    if (-not $binary) { throw "FFmpeg archive has no $name" }
    Copy-Item -LiteralPath $binary.FullName -Destination (Join-Path $target $name) -Force
}
$licenses = Join-Path $target 'licenses'
New-Item -ItemType Directory -Force $licenses | Out-Null
Get-ChildItem -LiteralPath $ffmpegDir -Recurse -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|README)' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $licenses ('ffmpeg-' + $_.Name)) -Force
}
foreach ($name in @('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'deno.exe')) {
    $file = Join-Path $target $name
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing tool: $name" }
}
Write-Host 'Pinned tools fetched and SHA-256 verified.'
