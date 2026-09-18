param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. "$PSScriptRoot\env.ps1"
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
$nodeExe = Join-Path $PSScriptRoot 'runtime\node\node.exe'
$pythonExe = Join-Path $PSScriptRoot 'runtime\python\python.exe'
$n8nCli = Join-Path $PSScriptRoot 'n8n\node_modules\n8n\bin\n8n'
foreach ($requiredFile in @($nodeExe,$pythonExe,$n8nCli)) {
    if (-not (Test-Path -LiteralPath $requiredFile)) { throw "Missing file: $requiredFile. Extract the complete folder first." }
}
New-Item -ItemType Directory -Path "$PSScriptRoot\logs","$PSScriptRoot\data" -Force | Out-Null
$serviceProcesses = @()
foreach ($servicePort in @(5678,5679,8765)) {
    $listeners = @(Get-NetTCPConnection -LocalPort $servicePort -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count) { throw "Port $servicePort is occupied. Stop the existing instance before starting this copy." }
}
$initMarker = Join-Path $PSScriptRoot 'data\initialized-v1.txt'
if (-not (Test-Path -LiteralPath $initMarker)) {
    Write-Host 'First run: creating local database and importing examples. Please wait.'
    $importMarker = Join-Path $PSScriptRoot 'data\examples-imported-v1.txt'
    if (-not (Test-Path -LiteralPath $importMarker)) {
    & $nodeExe $n8nCli import:workflow --separate "--input=$PSScriptRoot\workflows" *> "$PSScriptRoot\logs\initialize.log"
    if ($LASTEXITCODE -ne 0 -or -not ((Get-Content -LiteralPath "$PSScriptRoot\logs\initialize.log" -Raw -ErrorAction SilentlyContinue) -match [regex]::Escape('Successfully imported 2 workflows.'))) { throw 'Initialization failed. See logs\initialize.log.' }
    Set-Content -LiteralPath $importMarker -Value 'Examples imported. Preserve this marker with the database.'
    }
    & $nodeExe $n8nCli publish:workflow --id=trialPython01 *> "$PSScriptRoot\logs\publish.log"
    # n8n writes these logs as UTF-16LE; -Raw decodes them by BOM so the pattern is encoding-independent.
    $publishLog = Get-Content -LiteralPath "$PSScriptRoot\logs\publish.log" -Raw -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0 -or $publishLog -match '(?m)^Error') { throw 'Workflow publishing failed. See logs\publish.log.' }
    Set-Content -LiteralPath $initMarker -Value 'Initialized locally. Do not delete when upgrading.'
}
try {
    $pythonProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765','--workers','1' -WorkingDirectory "$PSScriptRoot\executor" -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot\logs\python.stdout.log" -RedirectStandardError "$PSScriptRoot\logs\python.stderr.log" -PassThru
    $serviceProcesses += $pythonProcess.Id
    $n8nProcess = Start-Process -FilePath $nodeExe -ArgumentList ('"' + $n8nCli + '" start') -WorkingDirectory "$PSScriptRoot\n8n" -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot\logs\n8n.stdout.log" -RedirectStandardError "$PSScriptRoot\logs\n8n.stderr.log" -PassThru
    $serviceProcesses += $n8nProcess.Id
    $serviceProcesses | ConvertTo-Json | Set-Content -LiteralPath "$PSScriptRoot\data\processes.json"
    Write-Host 'Starting local services. This can take several minutes on the first run.'
    $deadline = (Get-Date).AddMinutes(5)
    do {
        if ($pythonProcess.HasExited -or $n8nProcess.HasExited) { throw 'A service stopped unexpectedly. See logs.' }
        $ready = $false
        try {
            $null = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8765/api/tasks' -TimeoutSec 3
            $response = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:5678/form/workflow-python-trial' -TimeoutSec 3
            $ready = $response.StatusCode -eq 200 -and $response.Content.Contains('<form')
        } catch { }
        if ($ready) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if (-not $ready) { throw 'Startup timed out. See logs.' }
    Write-Host 'Ready: http://127.0.0.1:5678/form/workflow-python-trial'
    Write-Host 'Task records: http://127.0.0.1:8765  |  Workflow editor: http://127.0.0.1:5678'
    Write-Host 'Use stop.cmd when all executions have finished. Data stays in this folder.'
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5678/form/workflow-python-trial' }
} catch {
    foreach ($serviceProcessId in $serviceProcesses) { Stop-Process -Id $serviceProcessId -ErrorAction SilentlyContinue }
    throw
}
