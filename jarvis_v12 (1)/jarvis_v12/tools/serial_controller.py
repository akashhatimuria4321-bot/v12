"""
tools/serial_controller.py — JARVIS V12

UNIVERSAL SERIAL / USB CONTROLLER
"If it plugs into USB and talks serial, JARVIS can talk to it."

Supports:
  - Arduino (any board — Uno, Mega, Nano, Leonardo, Due, MKR...)
  - ESP32 / ESP8266 (any variant)
  - Raspberry Pi Pico
  - STM32
  - Any microcontroller with a serial/COM port
  - ANY USB serial device: 3D printers (Marlin G-code), CNC machines,
    oscilloscopes, custom hardware, home automation relays,
    smart power strips, LED controllers, sensor boards
  - Serial-based smart home devices (no cloud needed, no Alexa)

How home automation works WITHOUT Alexa:
  - Plug an Arduino/ESP32 relay module into USB
  - JARVIS sends commands over COM port
  - Relay switches lights, fans, AC, etc.
  - Full control over serial JSON or custom protocol
"""
from __future__ import annotations

import os, re, time, json, threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent

# ── pyserial ─────────────────────────────────────────────────────────────
try:
    import serial
    import serial.tools.list_ports
    SERIAL = True
except ImportError:
    SERIAL = False
    print("[SERIAL] pyserial not installed — pip install pyserial")

# ── esptool (for ESP32 flashing) ──────────────────────────────────────────
try:
    import esptool
    ESPTOOL = True
except ImportError:
    ESPTOOL = False

# ── arduino-cli check ────────────────────────────────────────────────────
import shutil


def _check_arduino_cli() -> Optional[str]:
    paths = [
        r"C:\Program Files\Arduino CLI\arduino-cli.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Arduino CLI\arduino-cli.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Arduino CLI\arduino-cli.exe"),
        r"C:\tools\arduino-cli.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


ARDUINO_CLI: Optional[str] = shutil.which("arduino-cli") or _check_arduino_cli()


# ══════════════════════════════════════════════════════════════════════════════
# PORT SCANNER — finds ALL serial devices
# ══════════════════════════════════════════════════════════════════════════════
class SerialDeviceInfo:
    def __init__(self, port: str, desc: str, hwid: str, vid: int = 0, pid: int = 0):
        self.port   = port
        self.desc   = desc
        self.hwid   = hwid
        self.vid    = vid
        self.pid    = pid

    @property
    def device_type(self) -> str:
        d = self.desc.lower()
        h = self.hwid.lower()
        if "arduino" in d or "uno" in d:                    return "Arduino Uno"
        if "arduino mega" in d or "2560" in h:              return "Arduino Mega"
        if "arduino nano" in d or "ch340" in d:             return "Arduino Nano/Clone"
        if "arduino leonardo" in d or "leo" in d:           return "Arduino Leonardo"
        if "esp32" in d or "cp210" in h:                    return "ESP32"
        if "esp8266" in d or "nodemcu" in d:                return "ESP8266/NodeMCU"
        if "esp32-s3" in d:                                 return "ESP32-S3"
        if "esp32-c3" in d:                                 return "ESP32-C3"
        if "pico" in d or "raspberry pi" in d:              return "Raspberry Pi Pico"
        if "stm32" in d or "st-link" in d:                  return "STM32"
        if "ftdi" in d or "ft232" in h:                     return "FTDI Serial Device"
        if "ch340" in d or "ch341" in d:                    return "CH340 Serial Device"
        if "pl2303" in h:                                    return "PL2303 Serial Device"
        if "silabs" in d or "cp2102" in d or "cp2104" in d: return "SiLabs CP210x Device"
        if "3d print" in d or "marlin" in d:                return "3D Printer"
        if "cnc" in d or "grbl" in d:                       return "CNC Machine"
        if "com" in self.port.lower():                       return "USB Serial Device"
        return "Unknown Serial Device"

    def __repr__(self):
        return f"{self.port}: {self.device_type} ({self.desc[:40]})"


def scan_serial_ports() -> List[SerialDeviceInfo]:
    """Scan all COM ports and return list of connected serial devices."""
    if not SERIAL:
        return []
    devices = []
    try:
        for port in serial.tools.list_ports.comports():
            dev = SerialDeviceInfo(
                port=port.device,
                desc=port.description or "",
                hwid=port.hwid or "",
                vid=getattr(port, "vid", 0) or 0,
                pid=getattr(port, "pid", 0) or 0,
            )
            devices.append(dev)
            print(f"[SERIAL] Found: {dev}")
    except Exception as e:
        print(f"[SERIAL] Scan error: {e}")
    return devices


def get_best_port_for(device_hint: str = "") -> Optional[str]:
    """Find the best matching COM port for a device type hint."""
    devices = scan_serial_ports()
    if not devices:
        return None

    hint = device_hint.lower()
    # Exact match first
    for dev in devices:
        if hint in dev.device_type.lower() or hint in dev.desc.lower():
            return dev.port

    # Any Arduino
    if any(w in hint for w in ["arduino", "uno", "mega", "nano", "leo"]):
        for dev in devices:
            if "arduino" in dev.device_type.lower() or \
               "ch340" in dev.device_type.lower() or \
               "cp210" in dev.device_type.lower():
                return dev.port

    # Any ESP
    if any(w in hint for w in ["esp", "nodemcu", "wemos"]):
        for dev in devices:
            if "esp" in dev.device_type.lower() or "cp210" in dev.device_type.lower():
                return dev.port

    # Return first available
    return devices[0].port


# ══════════════════════════════════════════════════════════════════════════════
# SERIAL COMMUNICATOR — send/receive on any COM port
# ══════════════════════════════════════════════════════════════════════════════
class SerialCommunicator:
    """
    Universal serial communication.
    Can send any command to any USB serial device:
    - Arduino commands (custom protocol)
    - G-code (3D printers, CNC)
    - AT commands (GSM modems)
    - JSON commands (smart home relays)
    - Raw bytes
    """

    def __init__(self):
        self._connections: Dict[str, serial.Serial] = {}

    def connect(self, port: str, baud: int = 9600,
                timeout: float = 3.0) -> Tuple[bool, str]:
        if not SERIAL:
            return False, "pyserial not installed — pip install pyserial"
        try:
            if port in self._connections and self._connections[port].is_open:
                return True, f"Already connected to {port}"
            s = serial.Serial(port, baud, timeout=timeout)
            time.sleep(2.0)  # Let device reset (Arduino resets on connect)
            self._connections[port] = s
            return True, f"Connected to {port} @ {baud} baud"
        except serial.SerialException as e:
            return False, f"Cannot open {port}: {e}"
        except Exception as e:
            return False, f"Serial connect error: {e}"

    def send(self, port: str, data: str,
             baud: int = 9600,
             wait_response: bool = True,
             response_timeout: float = 3.0) -> Tuple[bool, str]:
        """Send a string command and optionally read response."""
        if not SERIAL:
            return False, "pyserial not installed"
        try:
            if port not in self._connections or not self._connections[port].is_open:
                ok, msg = self.connect(port, baud)
                if not ok:
                    return False, msg

            s = self._connections[port]
            # Send with newline
            cmd = data.strip() + "\n"
            s.write(cmd.encode("utf-8", errors="replace"))
            s.flush()

            if not wait_response:
                return True, f"Sent to {port}: {data[:50]}"

            # Read response
            response = ""
            deadline = time.time() + response_timeout
            while time.time() < deadline:
                if s.in_waiting > 0:
                    chunk = s.read(s.in_waiting).decode("utf-8", errors="replace")
                    response += chunk
                    if "\n" in response:
                        break
                time.sleep(0.05)

            response = response.strip()
            return True, f"Sent: '{data[:40]}' | Response: '{response[:100]}'"

        except Exception as e:
            self._connections.pop(port, None)
            return False, f"Serial send error: {e}"

    def send_bytes(self, port: str, data: bytes, baud: int = 9600) -> Tuple[bool, str]:
        """Send raw bytes."""
        if not SERIAL:
            return False, "pyserial not installed"
        try:
            if port not in self._connections or not self._connections[port].is_open:
                ok, msg = self.connect(port, baud)
                if not ok:
                    return False, msg
            self._connections[port].write(data)
            return True, f"Sent {len(data)} bytes to {port}"
        except Exception as e:
            return False, f"Send bytes error: {e}"

    def read(self, port: str, timeout: float = 2.0) -> str:
        """Read data from port."""
        if not SERIAL or port not in self._connections:
            return ""
        try:
            s = self._connections[port]
            data = ""
            deadline = time.time() + timeout
            while time.time() < deadline:
                if s.in_waiting > 0:
                    data += s.read(s.in_waiting).decode("utf-8", errors="replace")
                time.sleep(0.05)
            return data.strip()
        except Exception:
            return ""

    def close(self, port: str):
        if port in self._connections:
            try:
                self._connections[port].close()
            except Exception:
                pass
            del self._connections[port]

    def close_all(self):
        for port in list(self._connections.keys()):
            self.close(port)


# Global communicator
_SERIAL = SerialCommunicator()


# ══════════════════════════════════════════════════════════════════════════════
# HOME AUTOMATION VIA USB SERIAL
# No Alexa, no cloud, no WiFi required.
# Uses a cheap Arduino/ESP32 relay board connected via USB.
# ══════════════════════════════════════════════════════════════════════════════
class HomeAutomationController:
    """
    Controls home appliances via USB-connected Arduino/ESP32 relay boards.
    
    Example Arduino sketch (upload once to relay board):
      void setup() { Serial.begin(9600); pinMode(2,OUTPUT); ... }
      void loop() {
        if (Serial.available()) {
          String cmd = Serial.readStringUntil('\\n');
          if (cmd == "LIGHT_ON")  digitalWrite(2, HIGH);
          if (cmd == "LIGHT_OFF") digitalWrite(2, LOW);
          if (cmd == "FAN_ON")    digitalWrite(3, HIGH);
          // etc...
          Serial.println("OK");
        }
      }
    
    Commands are fully customizable — JARVIS sends whatever the device expects.
    """

    # Default command map — user can customize
    DEFAULT_COMMANDS = {
        "light on":      "LIGHT_ON",
        "light off":     "LIGHT_OFF",
        "fan on":        "FAN_ON",
        "fan off":       "FAN_OFF",
        "ac on":         "AC_ON",
        "ac off":        "AC_OFF",
        "tv on":         "TV_ON",
        "tv off":        "TV_OFF",
        "all on":        "ALL_ON",
        "all off":       "ALL_OFF",
        "relay1 on":     "RELAY1_ON",
        "relay1 off":    "RELAY1_OFF",
        "relay2 on":     "RELAY2_ON",
        "relay2 off":    "RELAY2_OFF",
        "relay3 on":     "RELAY3_ON",
        "relay3 off":    "RELAY3_OFF",
        "relay4 on":     "RELAY4_ON",
        "relay4 off":    "RELAY4_OFF",
    }

    def __init__(self, settings: dict):
        self.settings = settings
        self._port = settings.get("home_automation_port", "")
        self._baud = settings.get("home_automation_baud", 9600)
        # Load custom commands from settings
        self._commands = dict(self.DEFAULT_COMMANDS)
        custom = settings.get("home_automation_commands", {})
        self._commands.update(custom)

    def _get_port(self) -> str:
        if self._port:
            return self._port
        # Auto-detect relay board
        port = get_best_port_for("arduino") or get_best_port_for("esp32")
        if port:
            self._port = port
        return self._port or ""

    def control(self, command: str) -> Tuple[bool, str]:
        """
        Send a home automation command.
        command: natural language e.g. 'turn on living room light'
        """
        port = self._get_port()
        cmd_str = self._resolve_command(command)

        if not port:
            # Try to find any serial device
            devices = scan_serial_ports()
            if not devices:
                return (False,
                    "Sir, koi USB relay board connected nahi hai. "
                    "Ek Arduino ya ESP32 relay module USB se connect karein "
                    "aur settings.json mein 'home_automation_port' set karein. "
                    f"Command tha: {cmd_str}")
            port = devices[0].port
            self._port = port

        ok, msg = _SERIAL.send(port, cmd_str, self._baud,
                               wait_response=True, response_timeout=2.0)
        if ok:
            return True, f"Home automation: '{command}' → '{cmd_str}' sent to {port}. {msg}"
        return False, f"Home automation error: {msg}"

    def _resolve_command(self, natural: str) -> str:
        """Map natural language to serial command."""
        nl = natural.lower().strip()

        # Direct match
        for phrase, cmd in self._commands.items():
            if phrase in nl:
                return cmd

        # Fuzzy: extract device + action
        action = "ON" if any(w in nl for w in ["on", "kholo", "chalu", "start",
                                                 "켜", "enable"]) else \
                 "OFF" if any(w in nl for w in ["off", "band", "stop",
                                                  "disable", "bujhao"]) else "TOGGLE"

        device_map = {
            "light":    "LIGHT",
            "bulb":     "LIGHT",
            "fan":      "FAN",
            "pankha":   "FAN",
            "ac":       "AC",
            "tv":       "TV",
            "television":"TV",
            "heater":   "HEATER",
            "pump":     "PUMP",
            "motor":    "MOTOR",
            "door":     "DOOR",
            "gate":     "GATE",
            "relay1":   "RELAY1",
            "relay2":   "RELAY2",
            "relay3":   "RELAY3",
            "relay4":   "RELAY4",
            "all":      "ALL",
            "sab":      "ALL",
            "everything":"ALL",
        }
        for word, device_cmd in device_map.items():
            if word in nl:
                return f"{device_cmd}_{action}"

        # Default: send as-is (let device handle it)
        return natural.upper().replace(" ", "_")

    def send_custom(self, port: str, command: str, baud: int = 9600) -> Tuple[bool, str]:
        """Send any raw command to any serial device."""
        if not port:
            port = self._get_port()
        if not port:
            return False, "No serial port specified"
        return _SERIAL.send(port, command, baud)

    def get_status(self) -> str:
        port = self._get_port()
        devices = scan_serial_ports()
        if devices:
            dev_list = ", ".join(f"{d.port}={d.device_type}" for d in devices)
            return f"Serial devices: {dev_list} | Home port: {port or 'auto'}"
        return "No serial devices connected"


# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL FIRMWARE UPLOADER
# Uploads code to ANY microcontroller board
# ══════════════════════════════════════════════════════════════════════════════

# Board FQBN map — covers every common board
BOARD_FQBN = {
    # Arduino classic
    "arduino uno":       "arduino:avr:uno",
    "uno":               "arduino:avr:uno",
    "arduino mega":      "arduino:avr:mega",
    "mega":              "arduino:avr:mega",
    "mega 2560":         "arduino:avr:mega:cpu=atmega2560",
    "arduino nano":      "arduino:avr:nano",
    "nano":              "arduino:avr:nano",
    "arduino nano old":  "arduino:avr:nano:cpu=atmega328old",
    "arduino leonardo":  "arduino:avr:leonardo",
    "leonardo":          "arduino:avr:leonardo",
    "arduino micro":     "arduino:avr:micro",
    "micro":             "arduino:avr:micro",
    "arduino pro mini":  "arduino:avr:pro:cpu=16MHzatmega328",
    "pro mini":          "arduino:avr:pro:cpu=16MHzatmega328",
    "arduino due":       "arduino:sam:arduino_due_x",
    "due":               "arduino:sam:arduino_due_x",
    "arduino mkr":       "arduino:samd:mkrwifi1010",
    # Arduino ESP boards
    "arduino nano esp32":"arduino:esp32:nano_nora",
    # ESP32 family
    "esp32":             "esp32:esp32:esp32",
    "esp32 dev":         "esp32:esp32:esp32",
    "esp32-wroom":       "esp32:esp32:esp32",
    "esp32-wrover":      "esp32:esp32:esp32wrover",
    "esp32-s2":          "esp32:esp32:esp32s2",
    "esp32-s3":          "esp32:esp32:esp32s3",
    "esp32-c3":          "esp32:esp32:esp32c3",
    "esp32-c6":          "esp32:esp32:esp32c6",
    "esp32-h2":          "esp32:esp32:esp32h2",
    "esp32 cam":         "esp32:esp32:esp32cam",
    "ttgo":              "esp32:esp32:esp32",
    "wemos d1 mini 32":  "esp32:esp32:wemos_d1_mini32",
    "lolin d32":         "esp32:esp32:lolin_d32",
    # ESP8266 family
    "esp8266":           "esp8266:esp8266:generic",
    "nodemcu":           "esp8266:esp8266:nodemcuv2",
    "nodemcu v2":        "esp8266:esp8266:nodemcuv2",
    "wemos d1 mini":     "esp8266:esp8266:d1_mini",
    "d1 mini":           "esp8266:esp8266:d1_mini",
    # Raspberry Pi Pico
    "pico":              "rp2040:rp2040:rpipico",
    "raspberry pi pico": "rp2040:rp2040:rpipico",
    "pico w":            "rp2040:rp2040:rpipicow",
    # STM32
    "stm32":             "STMicroelectronics:stm32:GenF1",
    "stm32 bluepill":    "STMicroelectronics:stm32:GenF1",
    "stm32 nucleo":      "STMicroelectronics:stm32:Nucleo_64",
    # Other
    "teensy 4.0":        "teensy:avr:teensy40",
    "teensy 4.1":        "teensy:avr:teensy41",
    "attiny85":          "ATTinyCore:avr:attinyx5",
}

# Default upload speeds per board family
BOARD_BAUD = {
    "arduino:avr":    115200,
    "esp32:esp32":    921600,
    "esp8266":        115200,
    "rp2040":         1200,  # Pico uses USB mass storage
    "STMicroelectronics": 115200,
}


def _get_fqbn(board_hint: str) -> Tuple[str, int]:
    """Get FQBN and upload baud from a human board name."""
    key = board_hint.lower().strip()
    fqbn = BOARD_FQBN.get(key, "")
    if not fqbn:
        for k, v in BOARD_FQBN.items():
            if key in k or k in key:
                fqbn = v
                break
    if not fqbn:
        fqbn = "arduino:avr:uno"  # Safe default

    baud = 115200
    for prefix, b in BOARD_BAUD.items():
        if fqbn.startswith(prefix):
            baud = b
            break
    return fqbn, baud


def upload_to_board(sketch_path: str = "",
                    sketch_code: str = "",
                    board: str = "arduino uno",
                    port: str = "",
                    libraries: List[str] = None) -> Tuple[bool, str]:
    """
    Universal firmware uploader.
    Works with any board supported by Arduino CLI.
    
    sketch_path: path to .ino or .cpp file
    sketch_code: raw code as string (saved to temp file)
    board:       human name like "esp32", "arduino nano", "pico"
    port:        COM port (auto-detected if empty)
    libraries:   extra libraries to install before compile
    """
    import subprocess, shutil, tempfile

    # Resolve port
    if not port:
        port = get_best_port_for(board)
        if not port:
            # Scan all
            devices = scan_serial_ports()
            if devices:
                port = devices[0].port
            else:
                return (False,
                    f"Sir, koi device USB pe nahi mila. "
                    f"{board} connect karein aur try karein.")

    fqbn, upload_baud = _get_fqbn(board)

    # Save code to temp file if given as string
    temp_dir = None
    if sketch_code and not sketch_path:
        temp_dir = tempfile.mkdtemp(prefix="jarvis_sketch_")
        sketch_name = Path(temp_dir) / "sketch" / "sketch.ino"
        sketch_name.parent.mkdir()
        sketch_name.write_text(sketch_code, encoding="utf-8")
        sketch_path = str(sketch_name.parent)

    if not sketch_path or not Path(sketch_path).exists():
        return False, f"Sketch file nahi mila: {sketch_path}"

    cli = ARDUINO_CLI
    if not cli:
        # Try arduino-cli in PATH
        cli = shutil.which("arduino-cli")

    if cli:
        try:
            # Install libraries if needed
            if libraries:
                for lib in libraries:
                    subprocess.run([cli, "lib", "install", lib],
                                   capture_output=True, text=True, timeout=60)

            # Compile
            print(f"[UPLOAD] Compiling for {board} ({fqbn})...")
            r = subprocess.run(
                [cli, "compile", "--fqbn", fqbn, sketch_path],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                return False, f"Compile error:\n{(r.stderr or r.stdout)[:400]}"

            # Upload
            print(f"[UPLOAD] Uploading to {port}...")
            r2 = subprocess.run(
                [cli, "upload", "-p", port, "--fqbn", fqbn,
                 "--upload-field", f"upload.speed={upload_baud}", sketch_path],
                capture_output=True, text=True, timeout=120
            )
            if r2.returncode == 0:
                return (True,
                    f"✅ Upload successful! {board} ({fqbn}) on {port}. "
                    f"Code run ho raha hai, Sir!")
            return False, f"Upload error:\n{(r2.stderr or r2.stdout)[:400]}"

        except subprocess.TimeoutExpired:
            return False, "Upload timeout (120s) — board connected hai?"
        except Exception as e:
            return False, f"Arduino CLI error: {e}"

    else:
        # No CLI — open IDE as fallback
        ide_paths = [
            r"C:\Program Files\Arduino IDE\Arduino IDE.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\arduino-ide\Arduino IDE.exe"),
            r"C:\Program Files (x86)\Arduino\arduino.exe",
        ]
        import subprocess
        for path in ide_paths:
            if os.path.exists(path):
                args = [path]
                if sketch_path:
                    args.append(sketch_path)
                subprocess.Popen(args)
                return (True,
                    f"Arduino IDE khul gaya, Sir! "
                    f"Manually upload karein: Tools > Board > {board}, "
                    f"Tools > Port > {port}, then Sketch > Upload. "
                    f"Tip: arduino-cli install karein for automatic upload: "
                    f"https://arduino.github.io/arduino-cli/")
        return (False,
            "Arduino IDE bhi nahi mila. Install karein: https://www.arduino.cc/en/software "
            "OR arduino-cli: https://arduino.github.io/arduino-cli/")


def send_serial_command(port: str, command: str, baud: int = 9600,
                        wait_response: bool = True) -> Tuple[bool, str]:
    """Send any command to any serial device."""
    if not port:
        devices = scan_serial_ports()
        if not devices:
            return False, "No serial devices connected"
        port = devices[0].port
    return _SERIAL.send(port, command, baud, wait_response)


def list_connected_serial_devices() -> Tuple[bool, str]:
    """List all USB serial devices currently connected."""
    devices = scan_serial_ports()
    if not devices:
        return False, "Koi USB serial device connected nahi hai, Sir"
    lines = [f"• {d.port}: {d.device_type} ({d.desc[:30]})"
             for d in devices]
    return True, "Connected USB devices:\n" + "\n".join(lines)

