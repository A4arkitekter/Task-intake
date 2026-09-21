# Registrerer Python-supervisoren ved login uden et vindue.
param([string]$InstallRoot = "")

$ErrorActionPreference = "Stop"

if ($InstallRoot) {
    $repo = [IO.Path]::GetFullPath($InstallRoot)
} else {
    $repo = (Resolve-Path "$PSScriptRoot\..").Path
}
if (Test-Path -LiteralPath (Join-Path $repo ".git") -PathType Container) {
    throw "Autostart maa ikke saettes fra Git-mappen ($repo). Koer scriptet fra den installerede kopi, typisk C:\apps\task-intake."
}
$python = Join-Path $repo ".venv\Scripts\python.exe"
$installer = Join-Path $repo "tools\install_autostart.py"
& $python $installer --root $repo
exit $LASTEXITCODE
