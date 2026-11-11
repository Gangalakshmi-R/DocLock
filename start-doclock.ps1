$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker was not found. Install and start Docker Desktop first.'
}

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env. Replace the example passwords and JWT secret, save it, then run this script again.' -ForegroundColor Yellow
    notepad .env
    exit 1
}

Write-Host 'Building and starting DocLock (PostgreSQL, Ollama, RAG backend and React frontend)...' -ForegroundColor Cyan
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed. Run: docker compose logs --tail=100' }

Write-Host 'Waiting for the backend and model setup. First startup downloads several GB of AI models.' -ForegroundColor Yellow
$ready = $false
for ($attempt = 0; $attempt -lt 180; $attempt++) {
    docker compose ps backend --format json | Select-String 'healthy' | Out-Null
    if ($LASTEXITCODE -eq 0 -and $?) { $ready = $true; break }
    Start-Sleep -Seconds 5
}

if (-not $ready) {
    Write-Host 'Services are still starting. Check progress with: docker compose ps' -ForegroundColor Yellow
    Write-Host 'If needed, inspect logs with: docker compose logs --tail=100 ollama-models backend' -ForegroundColor Yellow
} else {
    Write-Host 'Backend health check passed.' -ForegroundColor Green
}

Write-Host 'Frontend: http://localhost:3000' -ForegroundColor Green
Write-Host 'Backend health: http://localhost:8080/actuator/health' -ForegroundColor Cyan
Write-Host 'Login credentials are the DOCLOCK_USERNAME and DOCLOCK_PASSWORD values in .env.' -ForegroundColor Cyan
