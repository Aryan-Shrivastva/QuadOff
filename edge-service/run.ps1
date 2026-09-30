$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root 'edge-service'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
