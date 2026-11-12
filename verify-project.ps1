$ErrorActionPreference = 'Stop'
Write-Host 'DocLock preflight checks (Python FastAPI + React)' -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.11+ is required for local backend development.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20+ is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is required.' }
Write-Host '1/3 Checking Python backend syntax...' -ForegroundColor Yellow
python -m compileall -q backend/app
if ($LASTEXITCODE -ne 0) { throw 'Python backend syntax check failed.' }
Write-Host '2/3 Building React frontend...' -ForegroundColor Yellow
Push-Location frontend
try { npm install; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }; npm run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }
Write-Host '3/3 Checking Docker Compose configuration...' -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) { docker compose config --quiet; if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' } }
Write-Host 'Preflight checks passed. Run the Docker end-to-end smoke test after startup.' -ForegroundColor Green
