$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path (Join-Path $root 'node_modules'))) {
  npm install
}

$env:PYTHONPATH = Join-Path $root 'edge-service'
Write-Host 'Starting FieldNote edge service at http://127.0.0.1:8000 ...' -ForegroundColor Cyan
$api = Start-Process -FilePath python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $root -WindowStyle Hidden -PassThru

Write-Host 'Starting FieldNote UI at http://127.0.0.1:5173 ...' -ForegroundColor Green
npm run dev -- --host 127.0.0.1

if ($api -and -not $api.HasExited) {
  Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
