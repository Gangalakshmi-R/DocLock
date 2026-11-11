$ErrorActionPreference = 'Stop'

Write-Host 'DocLock preflight checks' -ForegroundColor Cyan

if (-not (Get-Command java -ErrorAction SilentlyContinue)) { throw 'Java 21 is required.' }
if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) { throw 'Maven 3.9+ is required. Install Maven and try again.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20+ is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is required.' }

Write-Host '1/3 Building Spring Boot backend...' -ForegroundColor Yellow
Push-Location backend
try { mvn -B clean package -DskipTests; if ($LASTEXITCODE -ne 0) { throw 'Backend build failed.' } }
finally { Pop-Location }

Write-Host '2/3 Building React frontend...' -ForegroundColor Yellow
Push-Location frontend
try { npm install; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }; npm run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }

Write-Host '3/3 Checking Docker Compose configuration...' -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' }
} else {
    Write-Host 'Docker is not installed; skipped Compose validation.' -ForegroundColor Yellow
}

Write-Host 'Preflight checks passed. This does not replace an end-to-end test with Docker services running.' -ForegroundColor Green
