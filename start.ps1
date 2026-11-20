# Starts both SentimentIQ servers in separate windows.
# Usage: .\start.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host "SentimentIQ backend: http://127.0.0.1:8000"
Write-Host "SentimentIQ frontend: http://localhost:5173"
