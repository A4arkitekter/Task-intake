@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Indtagelse - systemtjek
echo ========================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-SystemCheck.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
    echo Systemtjekket fandt fejl. Send kun fejlrapport.zip til IT.
) else (
    echo Systemtjekket er faerdigt. Ved problemer sendes kun fejlrapport.zip til IT.
)
echo Fejlrapporten indeholder ikke adgangskode, runtime, lydfiler eller databasen.
echo.
pause
exit /b %EXITCODE%
