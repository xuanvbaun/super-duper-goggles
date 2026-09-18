$ErrorActionPreference = 'Stop'
$expectedExecutables = @((Join-Path $PSScriptRoot 'runtime\node\node.exe'),(Join-Path $PSScriptRoot 'runtime\python\python.exe'))
$processFile = Join-Path $PSScriptRoot 'data\processes.json'
if (Test-Path -LiteralPath $processFile) {
    try {
        $processIds = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $processFile -Raw)
    } catch {
        Write-Warning "Could not read $processFile. Nothing was stopped by pid."
        $processIds = @()
    }
    foreach ($serviceProcessId in @($processIds)) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$serviceProcessId"
        if (-not $processInfo) { continue }
        if ($processInfo.ExecutablePath -notin $expectedExecutables) {
            Write-Warning "Process $serviceProcessId is no longer ours; skipping it."
            continue
        }
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$serviceProcessId")
        Stop-Process -Id $serviceProcessId -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            if ($child.ExecutablePath -in $expectedExecutables) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
        }
    }
    Remove-Item -LiteralPath $processFile -Force -ErrorAction SilentlyContinue
}
Write-Host 'Stopped. Your data remains in the data folder.'
