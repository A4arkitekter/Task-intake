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
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo FEJL: Den lokale Python-installation mangler. Koer SETUP.bat.
    set "EXITCODE=1"
    goto :result
)
"%PYTHON%" "%~dp0tools\publish_update.py"
set "EXITCODE=%ERRORLEVEL%"
:result
echo.
if not "%EXITCODE%"=="0" (
    echo Opdateringen blev ikke udgivet.
)
pause
exit /b %EXITCODE%
