$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$requiredFiles = @(
    ".env.example", ".gitignore",
    "SETUP.bat", "setup.ps1", "install.ps1",
    "SYSTEMTJEK.bat", "Run-SystemCheck.ps1", "check_setup.ps1",
    "START.bat", "Start-Indtagelse.ps1",
    "OPDATER.bat", "Update-Intake.ps1",
    "UDGIV OPDATERING.bat", "Publish-Update.ps1",
    "Test-GitContents.ps1", "Test-InstallState.ps1", "Test-RuntimeManifest.ps1",
    "New-RuntimeManifest.ps1",
    "install-contract.json", "runtime-contract.json",
    "requirements.txt", "requirements-lock.txt", "requirements-gpu.txt",
    "tools/Install-Helpers.ps1",
    "docs/source/KOLLEGA-START.md",
    "01-START-HER.md"
)

$forbiddenPatterns = @(
    '(^|/)runtime/',
    '(^|/)\.env$',
    '(^|/)\.venv/',
    '(^|/)data/audio/',
    '(^|/)data/models/',
    '(^|/)data/behandlet/',
    '(^|/)data/indbakke/',
    '(^|/)data/logs/',
    '\.sqlite3',
    '(^|/)install-state\.json$',
    '(^|/)setup-log\.txt$',
    '(^|/)systemtjek\.txt$',
    '(^|/)fejlrapport\.zip$',
    '(^|/)update-source\.txt$',
    '(^|/)\.update-state\.json$',
    '(^|/)\.browser-update-result\.json$',
    '\.(exe|dll|bin|wav|mp3|m4a|flac|ogg|wma|mp4|webm)$'
)

$candidates = @(& git ls-files)
if ($LASTEXITCODE -ne 0) { throw "Git kunne ikke vise projektets filer." }
$tracked = @($candidates | ForEach-Object { $_.Replace('\', '/') })
$visibleCandidates = @(& git ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) { throw "Git kunne ikke vise projektets filer." }
$visible = @($visibleCandidates | ForEach-Object { $_.Replace('\', '/') })
$errors = 0

foreach ($file in $requiredFiles) {
    if ($visible -notcontains $file) {
        Write-Host "FEJL Påkrævet Git-fil mangler: $file" -ForegroundColor Red
        $errors++
    }
}

foreach ($file in $tracked) {
    foreach ($pattern in $forbiddenPatterns) {
        if ($file -match $pattern) {
            Write-Host "FEJL Filen hører ikke til i Git: $file" -ForegroundColor Red
            $errors++
            break
        }
    }
}

if ($errors) {
    throw "Git-indholdet overholder ikke kontrakten ($errors fejl)."
}
Write-Host "Git-indholdet overholder kontrakten." -ForegroundColor Green
