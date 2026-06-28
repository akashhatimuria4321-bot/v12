@echo off
title JARVIS V12 — Installer
color 0B
echo.
echo  ==========================================
echo    JARVIS OMEGA V12 — Setup
echo    100%% FREE - No API Keys
echo  ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.14.5 from python.org
    pause
    exit /b 1
)
python --version

echo.
echo [1/6] Installing Python packages...
pip install -r requirements.txt

echo.
echo [2/6] Checking Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [!] Ollama not found. Download from: https://ollama.ai
    echo     After install, run: ollama pull llama3.2
) else (
    echo [OK] Ollama found
    echo [?] Pull AI model? (llama3.2 - ~2GB)
    set /p pull_model="Pull llama3.2 now? [y/n]: "
    if /i "%pull_model%"=="y" (
        ollama pull llama3.2
        ollama pull phi3:3.8b
    )
)

echo.
echo [3/6] Checking Tesseract OCR (for screen reading)...
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo [OK] Tesseract found
) else if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
    echo [OK] Tesseract found
) else (
    echo [!] Tesseract not found.
    echo     Download: https://github.com/tesseract-ocr/tesseract/releases
    echo     Install: tesseract-ocr-w64-setup-5.x.x.exe
)

echo.
echo [4/6] Creating data directories...
if not exist "data\screenshots" mkdir "data\screenshots"
if not exist "data\logs"        mkdir "data\logs"
if not exist "data\knowledge"   mkdir "data\knowledge"
echo [OK] Directories created

echo.
echo [5/6] Checking Arduino CLI (for firmware upload)...
arduino-cli version >nul 2>&1
if errorlevel 1 (
    echo [!] Arduino CLI not found.
    echo     Download: https://arduino.github.io/arduino-cli/
    echo     Or use Arduino IDE: https://www.arduino.cc/en/software
) else (
    echo [OK] Arduino CLI found
    echo [?] Install Arduino board cores?
    set /p install_cores="Install Arduino + ESP32 + ESP8266 cores? [y/n]: "
    if /i "%install_cores%"=="y" (
        arduino-cli core update-index
        arduino-cli core install arduino:avr
        arduino-cli core install esp32:esp32 --additional-urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
        arduino-cli core install esp8266:esp8266 --additional-urls https://arduino.esp8266.com/stable/package_esp8266com_index.json
        echo [OK] Board cores installed
    )
)

echo.
echo [6/6] Home Automation Setup (Optional)...
echo.
echo   If you have an Arduino/ESP32 relay board for home automation:
echo   1. Connect it via USB
echo   2. Edit config\settings.json
echo   3. Set "home_automation_port": "COM3"  (your COM port)
echo   4. Set "home_automation_baud": 9600
echo.
echo   No Alexa or WiFi needed — works 100%% via USB serial!
echo.

echo  ==========================================
echo    JARVIS V12 Setup Complete!
echo  ==========================================
echo.
echo  To start: python main.py
echo         OR: run.bat
echo.
echo  CONTROLS:
echo    SPACE     = Toggle voice listening (ON/OFF)
echo    ESC       = Ball mode (no black screen)
echo    Ctrl+J    = Open chat panel
echo    Ctrl+O    = Open output panel
echo    Ctrl+S    = Quick screenshot
echo    Ctrl+Q    = Quit
echo.
echo  BALL GLOW:
echo    ORANGE    = Listening (microphone ON)
echo    GREEN     = Working / Speaking
echo    BLUE      = Done / Ready
echo.
pause
