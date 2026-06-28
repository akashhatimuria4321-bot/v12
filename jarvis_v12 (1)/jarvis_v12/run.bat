@echo off
title JARVIS OMEGA V12
color 0B
cd /d "%~dp0"
echo  Starting JARVIS OMEGA V12...
echo  SPACE=Talk | ESC=Ball | Ctrl+J=Chat | Ctrl+Q=Quit
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] JARVIS crashed. Check the error above.
    echo Run install.bat to fix missing packages.
    pause
)
