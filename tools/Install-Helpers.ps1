function Get-FileSha256([string]$Path) {
    $Path = [IO.Path]::GetFullPath($Path)
    $stream = [System.IO.File]::OpenRead($Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

function Invoke-ProcessCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [int]$TimeoutSeconds = 15
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo

    try {
        $null = $process.Start()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            return [pscustomobject]@{ ExitCode = -1; Output = ""; Error = "Tidsgrænse overskredet" }
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output = $process.StandardOutput.ReadToEnd().Trim()
            Error = $process.StandardError.ReadToEnd().Trim()
        }
    } catch {
        return [pscustomobject]@{ ExitCode = -1; Output = ""; Error = $_.Exception.Message }
    } finally {
        $process.Dispose()
    }
}

function Get-NvidiaGpuName {
    $candidates = @()
    $command = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    if ($env:SystemRoot) { $candidates += (Join-Path $env:SystemRoot "System32\nvidia-smi.exe") }
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe") }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $name = & $candidate --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1
        if ($LASTEXITCODE -eq 0 -and $name) { return [string]$name }
    }

    try {
        $adapter = Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop |
            Where-Object { $_.Name -match "NVIDIA" } |
            Select-Object -First 1
        if ($adapter) { return [string]$adapter.Name }
    } catch { }
    return $null
}
