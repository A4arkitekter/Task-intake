@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Indtagelse - foerste gangs opsaetning
echo ========================================
echo.
echo VIGTIGT PAA EN NY COMPUTER:
echo   1. Programmet skal foerst hentes som ZIP fra GitHub og pakkes ud
echo      i C:\apps\task-intake. Kollegaen skal ikke have GitHub-adgang.
echo   2. Kopier HELE runtime-mappen fra:
echo      \\a4diskstation4\A4software\task-intake\runtime
echo   3. Foerst derefter maa denne SETUP.bat koeres.
echo.
echo VED EN OPDATERING:
echo   Koer kun SETUP.bat, hvis startfilen beder om det.
echo   Eksisterende runtime, .env og data bevares.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0.' -Recurse -File | Where-Object { $_.Extension -in '.ps1','.bat' } | Unblock-File" >nul 2>&1

if not exist "app\main.py" (
    echo STOP: SETUP.bat ligger ikke i programmets rodmappe.
    echo.
    echo GitHubs ZIP pakker ofte ud som en extra mappe, f.eks. Task-intake-main.
    echo Flyt indholdet, saa SETUP.bat og mappen app ligger i:
    echo   C:\apps\task-intake
    echo.
    pause
    exit /b 1
)

if not exist "runtime\runtime-manifest.json" (
    echo STOP: RUNTIME-MAPPEN MANGLER ELLER ER KOPIERET FORKERT.
    echo.
    echo GitHub indeholder IKKE runtime, modeller, EXE- eller DLL-filer.
    echo Kopier HELE mappen med navnet runtime fra:
    echo   \\a4diskstation4\A4software\task-intake\runtime
    echo ind i denne projektmappe.
    echo.
    echo Denne fil skal ende med at findes:
    echo   %CD%\runtime\runtime-manifest.json
    echo.
    echo Undgaa en dobbelt mappe som runtime\runtime\runtime-manifest.json.
    echo Se 01-START-HER.md.
    echo.
    pause
    exit /b 1
)

echo Installerer og kontrollerer Python, runtime og pakker ...
echo En detaljeret log gemmes i setup-log.txt.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 (
    echo.
    echo Installation fejlede. Se setup-log.txt og 01-START-HER.md.
    echo Koer SYSTEMTJEK.bat og send derefter kun fejlrapport.zip til IT.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Opsaetning faerdig
echo ========================================
echo.
echo Naeste skridt:
echo   1. Koer SYSTEMTJEK.bat.
echo   2. Start programmet med START.bat.
echo      Nye opdateringer vises automatisk i browseren.
echo.
pause
exit /b 0
