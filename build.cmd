@echo off
rem Compiles iSift into one folder: release\iSift\iSift.exe
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 (echo. & echo Build failed. See the messages above. & pause & exit /b 1)
echo.
echo Build finished. Open the release\iSift folder.
pause
