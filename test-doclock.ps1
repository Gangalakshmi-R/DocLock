# End-to-end smoke test. Run after Docker Compose reports healthy services.
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

$client = [System.Net.Http.HttpClient]::new()
try {
    Write-Host '1/7 Checking backend health...' -ForegroundColor Cyan
    $health = Invoke-RestMethod 'http://localhost:8080/actuator/health'
    if ($health.status -ne 'UP') { throw 'Backend health is not UP.' }

    Write-Host '2/7 Logging in...' -ForegroundColor Cyan
    $loginBody = @{ username = $username; password = $password } | ConvertTo-Json
    $login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" -ContentType 'application/json' -Body $loginBody
    $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $login.token)

    Write-Host '3/7 Checking ChromaDB...' -ForegroundColor Cyan
    $chromaHealth = Invoke-RestMethod 'http://localhost:8000/api/v2/heartbeat'

    Write-Host '4/7 Uploading a sample text document...' -ForegroundColor Cyan
    $sampleText = "DocLock smoke test document.`nThe project demonstration code is DOCLOCK-2026.`nThe AI architecture uses retrieval augmented generation, Nomic embeddings, and the Llama 3.1 language model.`nPostgreSQL stores documents and retrieved passages."
    $multipart = [System.Net.Http.MultipartFormDataContent]::new()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($sampleText)
    $filePart = [System.Net.Http.ByteArrayContent]::new($bytes)
    $filePart.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('text/plain')
    $multipart.Add($filePart, 'file', 'doclock-smoke-test.txt')
    $uploadResponse = $client.PostAsync("$baseUrl/documents", $multipart).GetAwaiter().GetResult()
    $uploadJson = $uploadResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $uploadResponse.IsSuccessStatusCode) { throw "Upload failed: $uploadJson" }
    $document = $uploadJson | ConvertFrom-Json
    $documentId = $document.id
    if (-not $documentId) { throw 'Upload did not return a document ID.' }

    Write-Host '5/7 Checking view and download endpoints...' -ForegroundColor Cyan
    foreach ($action in @('view', 'download')) {
        $response = $client.GetAsync("$baseUrl/documents/$documentId/$action").GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) { throw "Document $action endpoint failed." }
    }

    Write-Host '6/7 Asking the RAG chatbot...' -ForegroundColor Cyan
    $chatBody = @{ message = 'What is the project demonstration code?'; documentId = $documentId } | ConvertTo-Json
    $chatResponse = $client.PostAsync("$baseUrl/chat", [System.Net.Http.StringContent]::new($chatBody, [System.Text.Encoding]::UTF8, 'application/json')).GetAwaiter().GetResult()
    $chatJson = $chatResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $chatResponse.IsSuccessStatusCode) { throw "Chat failed: $chatJson" }
    $chat = $chatJson | ConvertFrom-Json
    if (-not $chat.citations -or $chat.citations.Count -lt 1) { throw 'Chat returned no source citations. Check embedding/retrieval and Ollama logs.' }
    Write-Host "AI answer: $($chat.answer)" -ForegroundColor Green

    Write-Host '7/7 Deleting the test document...' -ForegroundColor Cyan
    $deleteResponse = $client.DeleteAsync("$baseUrl/documents/$documentId").GetAwaiter().GetResult()
    if (-not $deleteResponse.IsSuccessStatusCode) { throw 'Document delete endpoint failed.' }

    Write-Host 'PASS: login, upload, view, download, RAG chat with citations and delete all worked.' -ForegroundColor Green
}
finally {
    $client.Dispose()
}
