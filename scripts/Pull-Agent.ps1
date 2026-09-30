$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    $settings = (& $pythonPath -c 'import json; from pipeline.core import CONFIG; print(json.dumps(CONFIG))') | ConvertFrom-Json
    $env:OLLAMA_HOST = $settings.services.ollama_url
    & (Join-Path $settings.paths.ollama_root 'ollama.exe') pull $settings.services.agent_model
    if ($LASTEXITCODE -ne 0) { throw 'Ollama model pull failed' }
} finally { Pop-Location }
