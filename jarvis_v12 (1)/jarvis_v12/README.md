# JARVIS OMEGA V12 🤖
### Advanced Local AI Assistant — 100% Free, No API Keys

---

## What's New in V12

| Feature | V10 | V12 |
|---|---|---|
| ESC key | Black screen + ball | **Ball ONLY — no black screen** |
| Ball size | 60px | **52px (smaller)** |
| SPACE key | Start listening only | **Toggle ON/OFF** |
| Ball glow | Static | **Orange=Listening, Green=Working, Blue=Done** |
| App control | Hardcoded shortcuts | **Universal — ANY app via screen vision** |
| App finder | Fixed list | **Finds ANY app: filesystem + registry + PATH** |
| Microcontrollers | Arduino Uno + ESP32 only | **ANY board: Uno/Mega/Nano/Leo/Due/ESP32/S2/S3/C3/Pico/STM32/Teensy...** |
| Home automation | Alexa HTTP (cloud) | **USB Serial relay board — no WiFi, no cloud** |
| Serial devices | Arduino only | **ANY USB serial: 3D printer, CNC, relay, custom hardware** |
| Screen reading | On-demand only | **Continuous — AI always knows what's on screen** |
| Web research | DuckDuckGo snippets | **Full page content + research caching** |
| Knowledge | Short-term only | **Permanent SQLite: tasks, UI elements, shortcuts, code** |

---

## Quick Start

```bat
# 1. Install everything
install.bat

# 2. Start Ollama (separate terminal)
ollama serve
ollama pull llama3.2

# 3. Run JARVIS
run.bat
```

---

## Controls

| Key | Action |
|---|---|
| `SPACE` | **Toggle voice listening ON/OFF** |
| `ESC` | Ball-only mode (hides full window, shows only ball) |
| `Ctrl+J` | Open/close chat panel |
| `Ctrl+O` | Open output panel |
| `Ctrl+S` | Quick screenshot |
| `Ctrl+T` | Settings |
| `Ctrl+Q` | Quit |

### Ball Glow States
- 🟠 **Orange** = Listening (microphone active, speak now)
- 🟢 **Green** = Working / Speaking (JARVIS is processing or talking)
- 🔵 **Blue** = Done / Ready (task complete)

---

## Universal App Control

JARVIS can control **ANY** app — not just a hardcoded list.

```
"Open Godot and create a new 2D scene"
"In DaVinci Resolve, click the Export button"
"Open VS Code, new file, write a Python hello world"
"In Blender, go to File > Export > OBJ"
"Open Adobe Illustrator and click the Pen tool"
```

How it works:
1. JARVIS opens the app
2. Takes a screenshot
3. OCR finds all visible text/buttons
4. Finds the button matching your intent
5. Clicks it
6. Saves the learned UI to memory for next time

---

## Universal Firmware Upload

Works with **any** microcontroller board:

```
"Upload this Arduino sketch to my Mega"
"Flash the ESP32-S3 with this code"
"Upload to my Raspberry Pi Pico"
"Compile and upload to STM32 bluepill"
"Flash the NodeMCU with my sketch"
```

**All supported boards:**
- Arduino: Uno, Mega, Mega2560, Nano, Leonardo, Micro, Pro Mini, Due, MKR...
- ESP32: DevKit, WROOM, WROVER, S2, S3, C3, C6, H2, CAM, TTGO, LoLin...
- ESP8266: Generic, NodeMCU v2, Wemos D1 Mini...
- Raspberry Pi Pico / Pico W
- STM32 (BluePill, Nucleo)
- Teensy 4.0, 4.1
- ATtiny85, ATtiny84

**Requirements:** Install [Arduino CLI](https://arduino.github.io/arduino-cli/) for automatic upload.

---

## Home Automation (No Alexa, No WiFi Needed!)

Uses a cheap Arduino/ESP32 relay board connected via USB.

### Setup (one-time):
1. Buy a 4-channel relay module (~₹200 on Amazon)
2. Connect it to Arduino/ESP32
3. Connect Arduino to your laptop via USB
4. Upload the sketch: `data/sketches/home_automation/home_automation.ino`
5. Connect relay outputs to your appliances

### Then just say:
```
"Light on karo"        → Relay 1 ON
"Fan band karo"        → Relay 2 OFF
"AC chalu karo"        → Relay 3 ON
"Sab kuch band karo"   → All relays OFF
"Ghar ka status batao" → STATUS query
```

Edit `config/settings.json` to set your COM port:
```json
"home_automation_port": "COM3",
"home_automation_baud": 9600
```

---

## USB / Pendrive

```
"Pendrive check karo"       → Lists connected USB drives
"Pendrive ki files dikhao"  → Lists all files
"project.zip USB se open karo" → Opens file from pendrive
```

---

## Serial Device Control

Send any command to any USB serial device:
```
"COM4 pe RESET bhejo"
"3D printer ko G28 command do"
"Serial device list karo"
```

---

## Web Research

```
"Latest Python 3.14 features kya hain?"
"DaVinci Resolve mein color grading kaise karte hain?"
"ESP32 WiFi code dikhao"
"Aaj ka news batao"
```

AI researches the web, saves results to memory, and learns for next time.

---

## Examples

### Video Editing
```
"DaVinci Resolve mein mera video import karo"
"Timeline mein Export button click karo"
"Render queue mein add karo"
```
*(If DaVinci Resolve not installed, JARVIS recommends Shotcut/Kdenlive/OpenShot)*

### Game Development  
```
"Godot open karo aur new 2D scene banao"
"Unity mein new project create karo"
"Blender mein cube add karo"
```

### Arduino/ESP32
```
"ESP32 mein ye code upload karo: [paste code]"
"Arduino Nano pe blink sketch upload karo"
"COM3 pe HELLO bhejo"
```

### Home Automation
```
"Light on karo"
"Raat ko sab band karo"
"Fan toggle karo"
```

### YouTube
```
"YouTube pe latest Arijit Singh song play karo"
"YouTube search: Python tutorial 2024"
```

---

## Project Structure

```
jarvis_v12/
├── main.py                     # Entry point
├── run.bat                     # One-click launch
├── install.bat                 # Setup script
├── requirements.txt
├── config/
│   └── settings.json           # All settings
├── core/
│   └── brain.py                # AI brain (Ollama + logic)
├── gui/
│   └── main_window.py          # PyQt6 GUI + ball
├── tools/
│   ├── automation.py           # Master action dispatcher
│   ├── universal_controller.py # OCR-based ANY-app control
│   ├── app_launcher.py         # Find/launch ANY app
│   └── serial_controller.py    # USB serial + firmware upload
├── speech/
│   ├── stt_engine.py           # Speech-to-text (free, Google)
│   └── tts_engine.py           # Text-to-speech (Edge TTS)
├── vision/
│   └── screen_vision.py        # Screen reading + OCR
├── learning/
│   └── trainer.py              # Persistent learning (SQLite)
└── data/
    ├── screenshots/
    ├── knowledge/              # SQLite DB (grows over time)
    └── sketches/
        ├── home_automation/    # Arduino relay sketch
        └── home_automation_esp32/
```

---

## Free Tools Required

| Tool | Purpose | Link |
|---|---|---|
| Ollama | Local AI models | https://ollama.ai |
| llama3.2 | Chat model | `ollama pull llama3.2` |
| Tesseract OCR | Screen reading | https://github.com/tesseract-ocr/tesseract/releases |
| Arduino CLI | Firmware upload | https://arduino.github.io/arduino-cli/ |

All Python packages: `pip install -r requirements.txt`

---

## Troubleshooting

**JARVIS not responding to voice:** Press SPACE, speak, press SPACE again to stop.

**App not found:** Say "scan all apps" — JARVIS will find everything installed.

**Arduino upload fails:** Install Arduino CLI from the link above.

**Home automation not working:** Check COM port in settings.json. Run "serial device list karo".

**Screen reading slow:** Install Tesseract OCR — link above.

**Ollama slow:** Use smaller model: change `"chat": "phi3:3.8b"` in settings.json.
