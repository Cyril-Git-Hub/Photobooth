@echo off
rem Construit l'executable Photo Booth dans dist\photobooth\ (a lancer depuis le dossier du projet).
setlocal
cd /d "%~dp0"
echo === Construction de l'executable Photo Booth ===
if not exist ".venv\Scripts\python.exe" (
  echo Environnement .venv introuvable. Cree-le d'abord :
  echo   py -3.12 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto erreur
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erreur
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean photobooth.spec
if errorlevel 1 goto erreur

rem Fichiers qui doivent se trouver a cote de l'executable
if exist models xcopy /E /I /Y models "dist\photobooth\models" >nul
if exist cadres xcopy /E /I /Y cadres "dist\photobooth\cadres" >nul
if exist themes xcopy /E /I /Y themes "dist\photobooth\themes" >nul
copy /Y MODE_EMPLOI.md "dist\photobooth\" >nul
copy /Y lancer.bat "dist\photobooth\" >nul

echo.
echo === Verification de l'executable (sans camera necessaire pour la plupart des controles) ===
"dist\photobooth\photobooth-outils.exe" --autotest
echo.
echo Termine. Copie le dossier dist\photobooth sur le PC de la fete, puis lance lancer.bat.
exit /b 0

:erreur
echo.
echo ECHEC de la construction : lis les messages ci-dessus.
exit /b 1
