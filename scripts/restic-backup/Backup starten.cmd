@echo off
REM Doppelklick startet das woechentliche Backup.
REM -ExecutionPolicy Bypass erlaubt nur fuer diesen einen Aufruf das Ausfuehren des Skripts.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1"
echo.
pause
