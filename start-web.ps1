param([int]$Port = 18765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$webPython = Join-Path $projectRoot '.venv-web\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $webPython)) {
    python -m venv (Join-Path $projectRoot '.venv-web')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
}
$requirements = Join-Path $projectRoot 'local_web\requirements.txt'
$stamp = Join-Path $projectRoot '.venv-web\requirements.sha256'
$expected = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
if (-not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $expected) {
    & $webPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Run this script again after fixing network access.' }
    Set-Content -LiteralPath $stamp -Value $expected -Encoding ascii
}
$arguments = @((Join-Path $projectRoot 'scripts\start-web.py'), '--port', "$Port")
if ($NoBrowser) { $arguments += '--no-browser' }
& $webPython @arguments
if ($LASTEXITCODE -ne 0) { throw 'Local Web service exited with an error.' }
