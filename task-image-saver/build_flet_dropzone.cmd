@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\build_flet_dropzone.ps1" %*
if errorlevel 1 exit /b 1
pause
