# Starter indtagelse på http://127.0.0.1:8000 og publicerer HTTPS via Cloudflare Tunnel.
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
cloudflared tunnel --url http://127.0.0.1:8000
