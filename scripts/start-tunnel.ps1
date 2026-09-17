# Starter indtagelse på den konfigurerede APP_PORT og publicerer HTTPS via Cloudflare Tunnel.
# Kræver: cloudflared i PATH (winget install Cloudflare.cloudflared)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared mangler. Installer med: winget install Cloudflare.cloudflared"
}

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Opret først .venv og kør pip install -r requirements.txt"
}

Start-Process -FilePath $python -ArgumentList "-m", "app" -WorkingDirectory $PWD
Start-Sleep -Seconds 2
$portText = & $python -c "from app.config import PORT; print(PORT)"
$port = 0
if ($LASTEXITCODE -ne 0 -or -not [int]::TryParse(("$portText").Trim(), [ref]$port)) {
    Write-Error "APP_PORT i .env er ugyldig."
}
cloudflared tunnel --url "http://127.0.0.1:$port"
