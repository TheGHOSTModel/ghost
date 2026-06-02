@echo off
cd /d "%~dp0"
echo Installing dependencies...
"C:\Program Files\Python314\python.exe" -m pip install -r requirements.txt -q
echo.
echo Starting Live Threat Radar server on http://localhost:8081
echo Press Ctrl+C to stop.
echo.
"C:\Program Files\Python314\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8081 --reload
