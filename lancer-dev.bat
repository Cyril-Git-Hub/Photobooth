@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Environnement Python introuvable : "%PYTHON%"
  echo Cree-le avec : py -3.12 -m venv .venv
  echo Puis installe les dependances : .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

"%PYTHON%" "%~dp0main.py" --windowed %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
