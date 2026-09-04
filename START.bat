@echo off
setlocal EnableExtensions
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Indtagelse.ps1"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
