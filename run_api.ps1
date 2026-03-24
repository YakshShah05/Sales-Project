# Run FastAPI backend locally
# Run from sales-mas root folder

.\sales_env\Scripts\Activate.ps1

$env:GROQ_API_KEY = (Get-Content .env | Where-Object { $_ -match "^GROQ_API_KEY=" }) -replace "^GROQ_API_KEY=", ""
$env:REDIS_URL = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
$env:VECTOR_STORE_PATH = "$PSScriptRoot\data\vector_store"
$env:UPLOAD_PATH = "$PSScriptRoot\data\uploads"
$env:API_BASE_URL = "http://localhost:8000"
$env:GROQ_MODEL = "llama3-8b-8192"
$env:EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
$env:PYTHONPATH = "$PSScriptRoot\backend"

New-Item -ItemType Directory -Force -Path ".\data\vector_store" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\uploads" | Out-Null

Write-Host "Starting FastAPI on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "Swagger docs: http://localhost:8000/docs" -ForegroundColor Cyan

cd backend
# uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload