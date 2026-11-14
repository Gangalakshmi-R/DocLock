$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker was not found. Install and start Docker Desktop first.' }
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env. Replace all CHANGE_ME values, save, then run this script again.' -ForegroundColor Yellow
    notepad .env
    exit 1
}
Write-Host 'Building and starting DocLock: PostgreSQL, Ollama, ChromaDB, Apache Tika, FastAPI and React...' -ForegroundColor Cyan
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed. Run: docker compose logs --tail=100' }
Write-Host 'First startup downloads Ollama models and builds the Python and React images. This may take several minutes.' -ForegroundColor Yellow
Write-Host 'Check services: docker compose ps' -ForegroundColor Cyan
Write-Host 'Frontend: http://localhost:3000' -ForegroundColor Green
Write-Host 'Backend health: http://localhost:8080/actuator/health' -ForegroundColor Green
Write-Host 'Login credentials: DOCLOCK_USERNAME and DOCLOCK_PASSWORD in .env' -ForegroundColor Cyan
