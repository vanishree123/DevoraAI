@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
set OLLAMA_URL=http://localhost:11434
set OLLAMA_MODEL=qwen2.5-coder:1.5b
echo Starting Devora AI...
echo Keep this window open while using the application.
start "" http://localhost:8501
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
if errorlevel 1 (
  echo.
  echo Devora AI stopped with an error. Copy the message above.
  pause
)
