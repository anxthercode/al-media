Set-StrictMode -Version Latest
$versionSource = Join-Path $PSScriptRoot '..\src\al_media\__init__.py'
$versionMatch = [regex]::Match((Get-Content -LiteralPath $versionSource -Raw), '__version__\s*=\s*"(\d+\.\d+\.\d+)"')
if (-not $versionMatch.Success) { throw 'Invalid application version' }
$versionMatch.Groups[1].Value
