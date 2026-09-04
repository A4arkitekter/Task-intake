@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Indtagelse - udgiv programopdatering
echo ========================================
echo.
echo Brug denne fil efter aendringerne er testet, committed og pushed.
echo Opdateringen udgives til:
echo   \\a4diskstation4\A4software\task-intake\updates
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Publish-Update.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
    echo Opdateringen blev ikke udgivet.
)
pause
exit /b %EXITCODE%
