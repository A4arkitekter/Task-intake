@echo off
setlocal EnableExtensions
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0.' -Recurse -File | Where-Object { $_.Extension -in '.ps1','.bat' } | Unblock-File" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Indtagelse.ps1"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
