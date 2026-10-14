@echo off
rem Lance la borne Photo Booth. Si elle s'arrete sur une erreur, elle est relancee (5 fois au maximum).
rem Un arret normal (mode admin > Quitter) ne relance rien.
cd /d "%~dp0"
set /a essais=0

:debut
start "" /wait "%~dp0photobooth.exe" %*
set code=%errorlevel%
if %code% EQU 0 goto fin
set /a essais+=1
if %essais% GEQ 5 goto trop
echo Photo Booth s'est arrete (code %code%). Relance dans 3 secondes...
timeout /t 3 /nobreak >nul
goto debut

:trop
echo Trop d'arrets successifs. Regarde le fichier logs\photobooth.log
pause

:fin
