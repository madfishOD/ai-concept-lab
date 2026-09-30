$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pidFile = Join-Path $projectRoot 'data\logs\app.pid'
try { $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3 } catch { $health = $null }
if ($health -and ($health.busy -or $health.queue_size -gt 0)) { throw 'Wait for active jobs before restarting the application.' }
if (Test-Path -LiteralPath $pidFile) {
    $appProcessId = [int](Get-Content -LiteralPath $pidFile)
    $appProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$appProcessId"
    if ($appProcess) {
        if ($appProcess.CommandLine -notlike '*uvicorn*pipeline.app:app*') { throw 'PID no longer belongs to Concept Lab. Refusing to stop it.' }
        Stop-Process -Id $appProcessId
        Wait-Process -Id $appProcessId -ErrorAction SilentlyContinue
    }
}
& (Join-Path $PSScriptRoot 'Start.ps1') -NoBrowser
