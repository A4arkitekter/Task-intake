@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Indtagelse - opdater programmet
echo ========================================
echo.
echo Henter godkendte opdateringer fra:
echo   \\a4diskstation4\A4software\task-intake\updates
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Intake.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
    echo Opdateringen blev ikke gennemfoert. Den tidligere version er bevaret.
)
pause
exit /b %EXITCODE%
