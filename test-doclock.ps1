# End-to-end smoke test. Run after Docker Compose reports healthy services.
# Covers: login, async upload + status polling, facts and expiry alerts, view/download, cited RAG answer, delete.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

$baseUrl = 'http://localhost:8080/api'
$envLines = Get-Content '.env'
function Read-EnvValue([string]$key, [string]$fallback) {
    $line = $envLines | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($key.Length + 1).Trim() }
    return $fallback
}

$username = Read-EnvValue 'DOCLOCK_USERNAME' 'admin'
$password = Read-EnvValue 'DOCLOCK_PASSWORD' ''
if ([string]::IsNullOrWhiteSpace($password)) { throw 'DOCLOCK_PASSWORD is missing in .env.' }
if ($password.StartsWith('pbkdf2_sha256$')) {
    # .env holds a hash, so the original password is needed to sign in.
    $secure = Read-Host 'DOCLOCK_PASSWORD in .env is a hash. Enter the original password' -AsSecureString
    $password = [System.Net.NetworkCredential]::new('', $secure).Password
}

$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromMinutes(10)
function Get-Json([string]$url) {
    $response = $client.GetAsync($url).GetAwaiter().GetResult()
    $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $response.IsSuccessStatusCode) { throw "GET $url failed ($($response.StatusCode)): $text" }
    return ($text | ConvertFrom-Json)
}

try {
    Write-Host '1/9 Checking backend health...' -ForegroundColor Cyan
    $health = Invoke-RestMethod 'http://localhost:8080/actuator/health'
    if ($health.status -ne 'UP') { throw 'Backend health is not UP.' }

    Write-Host '2/9 Logging in...' -ForegroundColor Cyan
    $loginBody = @{ username = $username; password = $password } | ConvertTo-Json
    $login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" -ContentType 'application/json' -Body $loginBody
    $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $login.token)

    Write-Host '3/9 Checking ChromaDB...' -ForegroundColor Cyan
    $chromaHealth = Invoke-RestMethod 'http://localhost:8000/api/v2/heartbeat'

    Write-Host '4/9 Uploading a sample document (returns immediately; processing runs in the background)...' -ForegroundColor Cyan
    $expiry = (Get-Date).AddDays(20).ToString('yyyy-MM-dd')
    $sampleText = "DocLock smoke test document.`nThe project demonstration code is DOCLOCK-2026.`nThe AI architecture uses retrieval augmented generation, Nomic embeddings, and the Llama 3.1 language model.`nPostgreSQL stores documents and retrieved passages.`nMembership expiry date: $expiry`nAnnual fee: Rs. 4,500"
    $multipart = [System.Net.Http.MultipartFormDataContent]::new()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($sampleText)
    $filePart = [System.Net.Http.ByteArrayContent]::new($bytes)
    $filePart.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('text/plain')
    $multipart.Add($filePart, 'file', 'doclock-smoke-test.txt')
    $uploadResponse = $client.PostAsync("$baseUrl/documents", $multipart).GetAwaiter().GetResult()
    $uploadJson = $uploadResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if ([int]$uploadResponse.StatusCode -ne 202) { throw "Expected HTTP 202 from upload, got $([int]$uploadResponse.StatusCode): $uploadJson" }
    $document = $uploadJson | ConvertFrom-Json
    $documentId = $document.id
    if (-not $documentId) { throw 'Upload did not return a document ID.' }

    Write-Host '5/9 Polling until background processing finishes...' -ForegroundColor Cyan
    $deadline = (Get-Date).AddMinutes(10)
    $lastStatus = ''
    while ($true) {
        $current = Get-Json "$baseUrl/documents/$documentId"
        if ($current.status -ne $lastStatus) { Write-Host "    status: $($current.status)"; $lastStatus = $current.status }
        if ($current.status -eq 'PROCESSED') { break }
        if ($current.status -eq 'FAILED') { throw "Processing failed: $($current.errorMessage)" }
        if ((Get-Date) -gt $deadline) { throw 'Timed out waiting for processing. Check: docker compose logs backend ollama' }
        Start-Sleep -Seconds 2
    }

    Write-Host '6/9 Checking extracted facts and the expiry alert...' -ForegroundColor Cyan
    $facts = (Get-Json "$baseUrl/documents/$documentId/facts").facts
    if (-not ($facts | Where-Object { $_.value -eq $expiry })) { throw "Expiry date $expiry was not extracted as a fact." }
    $mine = (Get-Json "$baseUrl/alerts").alerts | Where-Object { $_.documentId -eq $documentId -and $_.type -eq 'EXPIRY' }
    if (-not $mine) { throw 'No EXPIRY alert was created for the uploaded document.' }
    Write-Host "    alert: $($mine.title) on $($mine.deadline) ($($mine.daysLeft) days left, $($mine.status))" -ForegroundColor Green

    Write-Host '7/9 Checking view and download endpoints...' -ForegroundColor Cyan
    foreach ($action in @('view', 'download')) {
        $response = $client.GetAsync("$baseUrl/documents/$documentId/$action").GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) { throw "Document $action endpoint failed." }
    }

    Write-Host '8/9 Asking the RAG chatbot...' -ForegroundColor Cyan
    $chatBody = @{ message = 'What is the project demonstration code?'; documentId = $documentId } | ConvertTo-Json
    $chatResponse = $client.PostAsync("$baseUrl/chat", [System.Net.Http.StringContent]::new($chatBody, [System.Text.Encoding]::UTF8, 'application/json')).GetAwaiter().GetResult()
    $chatJson = $chatResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $chatResponse.IsSuccessStatusCode) { throw "Chat failed: $chatJson" }
    $chat = $chatJson | ConvertFrom-Json
    if (-not $chat.citations -or $chat.citations.Count -lt 1) { throw 'Chat returned no source citations. Check embedding/retrieval and Ollama logs.' }
    Write-Host "AI answer: $($chat.answer)" -ForegroundColor Green

    Write-Host '9/9 Deleting the test document (also removes its facts and alerts)...' -ForegroundColor Cyan
    $deleteResponse = $client.DeleteAsync("$baseUrl/documents/$documentId").GetAwaiter().GetResult()
    if (-not $deleteResponse.IsSuccessStatusCode) { throw 'Document delete endpoint failed.' }
    $left = (Get-Json "$baseUrl/alerts").alerts | Where-Object { $_.documentId -eq $documentId }
    if ($left) { throw 'Alerts for the deleted document were not removed.' }

    Write-Host 'PASS: login, async upload, status polling, facts and alerts, view, download, cited RAG chat and delete all worked.' -ForegroundColor Green
}
finally {
    $client.Dispose()
}
