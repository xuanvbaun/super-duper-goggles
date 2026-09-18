# Regenerate installer/app-overlay from the current application files.
# Run this after changing the executor, the workflows or the root scripts, so an install
# does not silently ship older code than the source tree.
#
# Keep this file ASCII-only: Windows PowerShell 5.1 decodes a .ps1 file without a UTF-8 BOM
# using the system ANSI code page, which corrupts non-ASCII literals.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$root = Split-Path -Parent $PSScriptRoot

# The user guide is the only root .md file that is neither README.md nor THIRD_PARTY_NOTICES.md;
# matched by extension so that its non-ASCII name never appears as a literal in this script.
$guides = @(Get-ChildItem -LiteralPath $root -File -Filter '*.md' | Where-Object { $_.Name -notin @('README.md', 'THIRD_PARTY_NOTICES.md') })
if ($guides.Count -ne 1) { throw "Expected exactly one non-README .md file in $root, found $($guides.Count)." }
$guideName = $guides[0].Name

$files = @(
    'env.ps1', 'start.ps1', 'stop.ps1', 'start.cmd', 'stop.cmd', 'open.cmd',
    'sync-workflows.ps1', 'sync-workflows.cmd', 'README.md', 'THIRD_PARTY_NOTICES.md', $guideName,
    'executor\app\__init__.py', 'executor\app\core.py', 'executor\app\main.py', 'executor\app\index.html',
    'executor\requirements-lock.txt',
    'workflows\01-python.json', 'workflows\02-deepseek.json'
)

$overlay = Join-Path $root 'installer\app-overlay'
if (Test-Path -LiteralPath $overlay) { Remove-Item -LiteralPath $overlay -Recurse -Force }
foreach ($relativeFile in $files) {
    $source = Join-Path $root $relativeFile
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing file: $relativeFile" }
    $destination = Join-Path $overlay $relativeFile
    $destinationDirectory = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $destinationDirectory)) { $null = [IO.Directory]::CreateDirectory($destinationDirectory) }
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
Write-Host "app-overlay refreshed from $root ($($files.Count) files)."
