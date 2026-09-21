$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

& "$repo\.venv\Scripts\python.exe" -m pytest backend/tests -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location frontend
npm run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Pop-Location

& "$repo\.venv\Scripts\python.exe" -m qa.runner --verbose
exit $LASTEXITCODE
