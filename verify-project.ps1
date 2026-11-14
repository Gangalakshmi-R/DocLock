$ErrorActionPreference = 'Stop'
Write-Host 'DocLock preflight checks (Python FastAPI + React)' -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.11+ is required for local backend development.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20+ is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is required.' }
Write-Host '1/4 Checking Python backend syntax...' -ForegroundColor Yellow
python -m compileall -q backend/app
if ($LASTEXITCODE -ne 0) { throw 'Python backend syntax check failed.' }
Write-Host '2/4 Running backend unit tests (offline: no Docker, Ollama or database needed)...' -ForegroundColor Yellow
python -c "import fastapi, pytest, httpx" 2>$null
if ($LASTEXITCODE -eq 0) {
    Push-Location backend
    try { python -m pytest -q; if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' } } finally { Pop-Location }
} else {
    Write-Host '    Skipped: run "pip install -r backend/requirements-dev.txt" once, then re-run this script.' -ForegroundColor DarkYellow
}
Write-Host '3/4 Building React frontend...' -ForegroundColor Yellow
Push-Location frontend
try { npm install; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }; npm run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }
Write-Host '4/4 Checking Docker Compose configuration...' -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) { docker compose config --quiet; if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' } }
Write-Host 'Preflight checks passed. Run the Docker end-to-end smoke test after startup.' -ForegroundColor Green
