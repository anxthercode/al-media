Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = py -3.12 --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required for building' }
    Write-Host $python
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
    & .\.venv\Scripts\python.exe -m pip install --isolated --index-url https://pypi.org/simple --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
    & .\.venv\Scripts\python.exe -m pip install --isolated --index-url https://pypi.org/simple -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'pinned dependency installation failed' }
    & .\.venv\Scripts\python.exe -m pip install -e . --no-deps
    if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
} finally { Pop-Location }
