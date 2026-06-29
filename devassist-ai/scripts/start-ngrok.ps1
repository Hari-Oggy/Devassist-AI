param(
    [ValidateSet("api", "frontend")]
    [string]$Target = "api",

    [int]$Port = 0,

    [string]$Url = $env:NGROK_URL
)

$ErrorActionPreference = "Stop"

$resolvedPort = $Port
if ($resolvedPort -eq 0) {
    if ($Target -eq "api") {
        $resolvedPort = 8000
    } else {
        $resolvedPort = 3000
    }
}

$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    Write-Host "ngrok CLI was not found." -ForegroundColor Red
    Write-Host "Install it, then run:" -ForegroundColor Yellow
    Write-Host "  ngrok config add-authtoken <your_ngrok_token>" -ForegroundColor White
    Write-Host ""
    Write-Host "Docs: https://ngrok.com/docs/getting-started" -ForegroundColor DarkGray
    exit 1
}

$isListening = Get-NetTCPConnection -LocalPort $resolvedPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $isListening) {
    Write-Host "Warning: nothing appears to be listening on port $resolvedPort." -ForegroundColor Yellow
    if ($Target -eq "api") {
        Write-Host "Start the backend first, for example:" -ForegroundColor Yellow
        Write-Host "  python -m uvicorn api.main:app --host 127.0.0.1 --port 8000" -ForegroundColor White
    } else {
        Write-Host "Start the frontend first, for example:" -ForegroundColor Yellow
        Write-Host "  cd frontend; npm run dev" -ForegroundColor White
    }
    Write-Host ""
}

$upstream = "http://127.0.0.1:$resolvedPort"
$arguments = @("http", $upstream)

if ($Url) {
    $arguments += "--url=$Url"
}

Write-Host ""
Write-Host "Starting ngrok for $Target at $upstream" -ForegroundColor Cyan
if ($Url) {
    Write-Host "Using ngrok URL: $Url" -ForegroundColor Cyan
}

if ($Target -eq "api") {
    Write-Host ""
    Write-Host "After ngrok starts, copy the HTTPS Forwarding URL and use:" -ForegroundColor Yellow
    Write-Host "  GitHub webhook: <forwarding-url>/api/v3/github/webhook" -ForegroundColor White
    Write-Host "  GitLab webhook:  <forwarding-url>/api/v3/gitlab/" -ForegroundColor White
    Write-Host ""
    Write-Host "Keep this terminal open while you want the public URL to work." -ForegroundColor DarkGray
} else {
    Write-Host ""
    Write-Host "After ngrok starts, open the HTTPS Forwarding URL to view the frontend." -ForegroundColor Yellow
    Write-Host "Keep this terminal open while you want the public URL to work." -ForegroundColor DarkGray
}

& $ngrok.Source @arguments
