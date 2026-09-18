# Re-import the shipped example workflows into the local n8n database and republish them.
# start.ps1 only imports on the very first run, so an updated workflow file would otherwise
# be ignored on an existing data folder.
param([switch]$Force)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. "$PSScriptRoot\env.ps1"
$nodeExe = Join-Path $PSScriptRoot 'runtime\node\node.exe'
$n8nCli = Join-Path $PSScriptRoot 'n8n\node_modules\n8n\bin\n8n'
foreach ($servicePort in @(5678,5679,8765)) {
    if (@(Get-NetTCPConnection -LocalPort $servicePort -State Listen -ErrorAction SilentlyContinue).Count) {
        throw "Port $servicePort is occupied. Run stop.cmd first: importing while n8n is running has no effect."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'data\initialized-v1.txt'))) { throw 'Not initialized yet. Run start.cmd first.' }
if (-not $Force) {
    Write-Host 'This replaces the stored copy of the example workflows with the files in the workflows folder.'
    Write-Host 'Any change you made to them inside the n8n editor, including credential choices, is lost.'
    $answer = Read-Host 'Continue? Type y to proceed'
    if ($answer -ne 'y') { Write-Host 'Cancelled. Nothing was changed.'; exit 0 }
}
New-Item -ItemType Directory -Path "$PSScriptRoot\logs" -Force | Out-Null
& $nodeExe $n8nCli import:workflow --separate "--input=$PSScriptRoot\workflows" *> "$PSScriptRoot\logs\sync.log"
$syncLog = Get-Content -LiteralPath "$PSScriptRoot\logs\sync.log" -Raw -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0 -or -not ($syncLog -match [regex]::Escape('Successfully imported 2 workflows.'))) { throw 'Import failed. See logs\sync.log.' }
& $nodeExe $n8nCli publish:workflow --id=trialPython01 *> "$PSScriptRoot\logs\publish.log"
$publishLog = Get-Content -LiteralPath "$PSScriptRoot\logs\publish.log" -Raw -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0 -or $publishLog -match '(?m)^Error') { throw 'Publishing failed. See logs\publish.log.' }
Write-Host 'Workflows synced from the workflows folder. Run start.cmd to use them.'
