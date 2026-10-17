Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'build\InnoSetup'
if (Test-Path (Join-Path $target 'ISCC.exe')) { return }
$url = 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe'
$expected = '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
New-Item -ItemType Directory -Force (Join-Path $root 'build') | Out-Null
$archive = Join-Path $root 'build\innosetup-6.7.3.exe'
if (-not (Test-Path $archive)) { Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Inno Setup SHA-256 mismatch' }
$signature = Get-AuthenticodeSignature -LiteralPath $archive
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') { throw 'Inno Setup signature invalid' }
$arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', ('/DIR="' + $target + '"'))
$process = Start-Process -FilePath $archive -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $target 'ISCC.exe'))) { throw 'Inno Setup installation failed' }
