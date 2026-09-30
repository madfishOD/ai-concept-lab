param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements first. See README.md.' }
$logDir = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Push-Location $projectRoot
try { $configuration = & $pythonPath -c 'import json; from pipeline.core import CONFIG; print(json.dumps(CONFIG))' } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Run Start.ps1 from the project directory.' }
$settings = $configuration | ConvertFrom-Json
function Test-Endpoint([string]$Address) { try { Invoke-RestMethod -Uri $Address -TimeoutSec 2 | Out-Null; return $true } catch { return $false } }
if (-not (Test-Endpoint ($settings.services.ollama_url + '/api/tags'))) {
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = $settings.paths.ollama_models
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_KEEP_ALIVE = '0'
    $ollamaProcess = Start-Process -FilePath (Join-Path $settings.paths.ollama_root 'ollama.exe') -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'ollama.stdout.log') -RedirectStandardError (Join-Path $logDir 'ollama.stderr.log')
    $ollamaProcess.Id | Set-Content -LiteralPath (Join-Path $logDir 'ollama.pid')
}
if (-not (Test-Endpoint ($settings.services.comfy_url + '/system_stats'))) {
    $comfyProcess = Start-Process -FilePath (Join-Path $settings.paths.comfy_root 'python_embeded\python.exe') -ArgumentList '-s','ComfyUI\main.py','--windows-standalone-build','--listen','127.0.0.1','--port','8188','--disable-auto-launch' -WorkingDirectory $settings.paths.comfy_root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'comfy.stdout.log') -RedirectStandardError (Join-Path $logDir 'comfy.stderr.log')
    $comfyProcess.Id | Set-Content -LiteralPath (Join-Path $logDir 'comfy.pid')
}
if (-not (Test-Endpoint 'http://127.0.0.1:8765/api/health')) {
    $appProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','pipeline.app:app','--host','127.0.0.1','--port','8765' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'app.stdout.log') -RedirectStandardError (Join-Path $logDir 'app.stderr.log')
    $appProcess.Id | Set-Content -LiteralPath (Join-Path $logDir 'app.pid')
}
Write-Output 'Concept Lab: http://127.0.0.1:8765'
Write-Output 'ComfyUI: http://127.0.0.1:8188'
Write-Output "Logs: $logDir"
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
