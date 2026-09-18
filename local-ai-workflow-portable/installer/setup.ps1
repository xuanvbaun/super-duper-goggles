param([string]$ParentDirectory, [switch]$NoStart)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
# Use the tar.exe shipped with Windows. A GNU tar from Git/MSYS/Cygwin earlier on
# PATH reads "E:\..." as a remote host and fails the extraction.
$tarExe = Join-Path $env:SystemRoot 'System32\tar.exe'
if (-not (Test-Path -LiteralPath $tarExe)) { throw "Windows built-in tar.exe was not found at $tarExe. Windows 10 version 1803 or newer is required." }
$payload = Join-Path $PSScriptRoot 'payload.tar.xz'
$expected = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'payload.sha256') -Raw).Trim()
if ($expected -notmatch '^[a-f0-9]{64}$') { throw 'Invalid payload checksum file.' }
Write-Host 'Checking installer integrity...'
if ((Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Installer is damaged. Please download it again.' }
if (-not $ParentDirectory) {
    $defaultParent = if (Test-Path -LiteralPath 'E:\') { 'E:\AI-Apps' } else { "$env:SystemDrive\AI-Apps" }
    $ParentDirectory = Read-Host "Install parent folder (press Enter for $defaultParent)"
    if (-not $ParentDirectory) { $ParentDirectory = $defaultParent }
}
if ($ParentDirectory -notmatch '^[A-Za-z]:[\\/]') { throw 'Use a full local path such as E:\AI-Apps.' }
$parentPath = [IO.Path]::GetFullPath($ParentDirectory)
$target = Join-Path $parentPath 'AI-Workflow-Portable'
if (Test-Path -LiteralPath $target) { throw "Destination already exists: $target. It was NOT overwritten. Choose a different parent folder." }
$null = [IO.Directory]::CreateDirectory($parentPath)
Write-Host 'Extracting bundled runtimes and application. This can take several minutes.'
& $tarExe -xf $payload -C $parentPath
if ($LASTEXITCODE -ne 0) { throw 'Extraction failed. Do not run the incomplete folder.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'stop.ps1') -Destination (Join-Path $target 'stop.ps1') -Force
# The payload only carries the slow-moving runtimes (2 GiB). Application code lives in
# app-overlay so a rebuilt payload is not required for every script or workflow change.
$overlay = Join-Path $PSScriptRoot 'app-overlay'
if (Test-Path -LiteralPath $overlay) {
    Write-Host 'Applying current application files...'
    Get-ChildItem -LiteralPath $overlay -Recurse -File | ForEach-Object {
        $relativePath = $_.FullName.Substring($overlay.Length).TrimStart('\')
        $destinationFile = Join-Path $target $relativePath
        $destinationDirectory = Split-Path -Parent $destinationFile
        if (-not (Test-Path -LiteralPath $destinationDirectory)) { $null = [IO.Directory]::CreateDirectory($destinationDirectory) }
        Copy-Item -LiteralPath $_.FullName -Destination $destinationFile -Force
    }
} else {
    Write-Warning 'app-overlay is missing; the installed copy keeps the files from the payload.'
}
foreach ($relativeFile in @('start.ps1','env.ps1','executor\app\main.py','workflows\01-python.json','runtime\node\node.exe','runtime\python\python.exe','n8n\node_modules\n8n\bin\n8n')) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $relativeFile))) { throw "Missing extracted file: $relativeFile" }
}
Write-Host "Installed: $target"
if (-not $NoStart) { & (Join-Path $target 'start.ps1') }
