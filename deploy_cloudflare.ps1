param([int]$Port = 8011)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$distDir = Join-Path $root "frontend\dist"

function New-Secret([int]$Bytes = 32) {
    $buffer = [byte[]]::new($Bytes)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

if (-not (Test-Path $distDir)) {
    throw "Frontend build not found. Run: cd frontend; npm install; npm run build"
}

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
        (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe")
    )
    $cloudflared = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $cloudflared) {
    Write-Host "cloudflared is not installed. Install it with:"
    Write-Host "  winget install --id Cloudflare.cloudflared"
    throw "cloudflared is required for the free tunnel."
}

$env:SENTIMENTIQ_AUTH_ENABLED = "true"
if (-not $env:SENTIMENTIQ_ADMIN_USER) { $env:SENTIMENTIQ_ADMIN_USER = "admin" }

$generatedPassword = $false
if (-not $env:SENTIMENTIQ_ADMIN_PASSWORD) {
    $env:SENTIMENTIQ_ADMIN_PASSWORD = New-Secret 24
    $generatedPassword = $true
}
if (-not $env:SENTIMENTIQ_SECRET_KEY) {
    $env:SENTIMENTIQ_SECRET_KEY = New-Secret 48
}
$env:SENTIMENTIQ_CORS_ORIGINS = "http://localhost:$Port,http://127.0.0.1:$Port"

Write-Host "Starting SentimentIQ on http://127.0.0.1:$Port"
$backend = Start-Process `
    -FilePath python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port.ToString()) `
    -WorkingDirectory $backendDir `
    -PassThru

try {
    $health = $null
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        } catch {
            $health = $null
        }
    } while (-not $health -and (Get-Date) -lt $deadline -and -not $backend.HasExited)

    if (-not $health) {
        throw "Backend did not become healthy. Check the uvicorn process and try again."
    }

    if ($generatedPassword) {
        Write-Host ""
        Write-Host "Initial admin  : $env:SENTIMENTIQ_ADMIN_USER"
        Write-Host "Initial password: $env:SENTIMENTIQ_ADMIN_PASSWORD"
        Write-Host "This seeds the first account only. If accounts already exist, sign in with one of them or reset a password in Settings."
        Write-Host ""
    }

    Write-Host "Starting Cloudflare quick tunnel."
    Write-Host "Share the https://*.trycloudflare.com URL printed below."
    Write-Host "Keep this window open. Press Ctrl+C to stop both the tunnel and backend."
    & $cloudflared tunnel --url "http://127.0.0.1:$Port"
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
