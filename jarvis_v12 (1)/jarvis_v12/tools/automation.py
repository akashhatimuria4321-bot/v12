"""
tools/automation.py — JARVIS OMEGA V12 (COMPLETE REWRITE)

PHILOSOPHY:
  "If a human can see it, click it, or type it — JARVIS can do it."

  No hardcoded app shortcuts.
  No locked-to-specific-device logic.
  No Alexa assumption.

  Instead:
  - UniversalAppController: screen-reads + OCR to navigate ANY app
  - UniversalAppLauncher:   finds ANY app on the system via FS/Registry/PATH
  - SerialController:       talks to ANY USB device (not just Arduino)
  - HomeAutomation:         via USB relay board (no cloud, no Alexa)

All actions return (bool, str) = (success, message).
"""
from __future__ import annotations

import os, re, time, json, subprocess, threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

BASE = Path(__file__).resolve().parent.parent

# ── Import our new universal modules ─────────────────────────────────────
from tools.app_launcher      import (launch_app, close_app_by_name,
                                     get_running_apps, get_all_installed_apps,
                                     _open_in_best_browser, find_app_path,
                                     WEB_FALLBACKS)
from tools.universal_controller import (click_ui_element, find_and_type,
                                         read_screen_and_describe,
                                         list_all_ui_elements_text,
                                         get_full_screen_text, capture_screen,
                                         UniversalAppController, PYAUTOGUI)
from tools.serial_controller import (scan_serial_ports, list_connected_serial_devices,
                                      send_serial_command, upload_to_board,
                                      HomeAutomationController,
                                      _SERIAL as _SER)

# ── Optional deps ─────────────────────────────────────────────────────────
try:
    import pyautogui as _pag
    _pag.FAILSAFE = True
    _pag.PAUSE    = 0.06
except ImportError:
    _pag = None

try:
    import pygetwindow as gw
    PYGETWINDOW = True
except ImportError:
    PYGETWINDOW = False

try:
    import psutil
    PSUTIL = True
except ImportError:
    PSUTIL = False

try:
    from PIL import ImageGrab
    PIL = True
except ImportError:
    PIL = False

try:
    import ctypes
    CTYPES = True
except Exception:
    CTYPES = False


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_coords(s: str) -> Tuple[Optional[int], Optional[int]]:
    m = re.search(r'(\d+)[,\s]+(\d+)', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _get_active_title() -> str:
    if CTYPES:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            l    = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf  = ctypes.create_unicode_buffer(l + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, l + 1)
            return buf.value
        except Exception:
            pass
    return ""


def _hotkey(*keys) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    try:
        _pag.hotkey(*keys)
        return True, f"Hotkey: {'+'.join(keys)}"
    except Exception as e:
        return False, f"Hotkey error: {e}"


def _press_key(key: str) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    try:
        _pag.press(key)
        return True, f"Key pressed: {key}"
    except Exception as e:
        return False, f"Key press error: {e}"


def _type_text(text: str) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    try:
        time.sleep(0.2)
        _pag.write(str(text), interval=0.022)
        return True, f"Typed: {str(text)[:60]}"
    except Exception as e:
        return False, f"Type error: {e}"


def _screenshot() -> Tuple[bool, str]:
    shots = BASE / "data" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    fname = shots / f"shot_{datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        img = capture_screen()
        if img:
            img.save(str(fname))
            return True, f"Screenshot: {fname.name}"
        if _pag:
            _pag.screenshot(str(fname))
            return True, f"Screenshot: {fname.name}"
        return False, "Screenshot nahi hua"
    except Exception as e:
        return False, f"Screenshot error: {e}"


def _system_info() -> Tuple[bool, str]:
    parts = []
    try:
        if PSUTIL:
            cpu  = psutil.cpu_percent(0.4)
            mem  = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")
            parts += [
                f"CPU {cpu:.0f}%",
                f"RAM {mem.percent:.0f}% ({mem.used>>20}MB/{mem.total>>20}MB)",
                f"Disk C: {disk.free>>30}GB free",
            ]
        import platform as pl
        parts.append(f"OS: {pl.system()} {pl.release()}")
    except Exception as e:
        parts.append(f"Error: {e}")
    return True, " | ".join(parts)


def _scroll(direction: str, amount: int = 3) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    _pag.scroll(amount if direction == "up" else -amount)
    return True, f"Scrolled {direction}"


# ══════════════════════════════════════════════════════════════════════════════
# PLAY MUSIC — smart: Spotify if installed, else YouTube
# ══════════════════════════════════════════════════════════════════════════════
def _play_music(query: str) -> Tuple[bool, str]:
    spotify = find_app_path("spotify")
    if spotify and os.path.exists(spotify):
        try:
            os.startfile(f"spotify:search:{query.replace(' ', '%20')}")
            return True, f"Spotify pe '{query}' play ho raha hai, Sir!"
        except Exception:
            pass
    # Fallback YouTube
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    return _open_in_best_browser(url)


# ══════════════════════════════════════════════════════════════════════════════
# YOUTUBE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _search_youtube(query: str) -> Tuple[bool, str]:
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    ok, msg = _open_in_best_browser(url)
    return ok, f"YouTube pe '{query}' search ho raha hai, Sir!"


def _click_first_video() -> Tuple[bool, str]:
    """After YouTube search loads, click first video result."""
    time.sleep(3.0)
    # Try OCR-based click
    ok, msg = click_ui_element("Watch", wait_after=0.5)
    if ok:
        return ok, f"YouTube pehla video play ho raha hai, Sir! {msg}"
    # Fallback: click approximate position of first video
    if _pag:
        sw, sh = _pag.size()
        _pag.click(int(sw * 0.33), int(sh * 0.40))
        return True, "YouTube pe pehla video click kiya, Sir!"
    return False, "Video click nahi hua"


def _search_web(query: str) -> Tuple[bool, str]:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    return _open_in_best_browser(url)


# ══════════════════════════════════════════════════════════════════════════════
# VOLUME / SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
def _volume_up(steps: int = 3) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    for _ in range(steps):
        _pag.press("volumeup")
    return True, "Volume badhaya, Sir!"


def _volume_down(steps: int = 3) -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    for _ in range(steps):
        _pag.press("volumedown")
    return True, "Volume ghataaya, Sir!"


def _mute() -> Tuple[bool, str]:
    if not _pag:
        return False, "pyautogui not installed"
    _pag.press("volumemute")
    return True, "Muted, Sir!"


def _lock_screen() -> Tuple[bool, str]:
    try:
        if CTYPES:
            ctypes.windll.user32.LockWorkStation()
        else:
            subprocess.run("rundll32 user32.dll,LockWorkStation", shell=True)
        return True, "Screen lock, Sir!"
    except Exception as e:
        return False, f"Lock error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# USB / PENDRIVE
# ══════════════════════════════════════════════════════════════════════════════
def _list_usb_drives() -> Tuple[bool, str]:
    if not CTYPES:
        return False, "ctypes unavailable"
    try:
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                letter = chr(65 + i) + ":\\"
                t = ctypes.windll.kernel32.GetDriveTypeW(letter)
                if t == 2:
                    drives.append(letter)
        if drives:
            return True, f"USB drives: {', '.join(drives)}"
        return False, "Koi USB drive connected nahi, Sir"
    except Exception as e:
        return False, f"USB detect error: {e}"


def _list_usb_files(drive: str = "") -> Tuple[bool, str]:
    if not drive:
        if CTYPES:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    letter = chr(65 + i) + ":\\"
                    if ctypes.windll.kernel32.GetDriveTypeW(letter) == 2:
                        drive = letter
                        break
    if not drive:
        return False, "USB drive nahi mila"
    try:
        files = [f.name for f in Path(drive).iterdir()][:60]
        return True, f"{drive} files: {', '.join(files[:25])}"
    except Exception as e:
        return False, f"USB list error: {e}"


def _open_usb_file(filename: str) -> Tuple[bool, str]:
    if CTYPES:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                letter = chr(65 + i) + ":\\"
                if ctypes.windll.kernel32.GetDriveTypeW(letter) == 2:
                    for f in Path(letter).rglob(filename):
                        try:
                            os.startfile(str(f))
                            return True, f"USB file khuli: {f.name}"
                        except Exception as e:
                            return False, f"Open error: {e}"
    return False, f"'{filename}' USB pe nahi mila"


# ══════════════════════════════════════════════════════════════════════════════
# CODE RUNNERS
# ══════════════════════════════════════════════════════════════════════════════
def _run_python(code: str) -> Tuple[bool, str]:
    tmp = BASE / "data" / "temp_script.py"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_text(code, encoding="utf-8")
        r = subprocess.run(["python", str(tmp)],
                           capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out[:500] or "Script complete"
    except subprocess.TimeoutExpired:
        return False, "Script timeout (30s)"
    except Exception as e:
        return False, f"Run error: {e}"


def _run_command(cmd: str) -> Tuple[bool, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out[:500] or "Done"
    except Exception as e:
        return False, f"Command error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# WINDOW MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
def _focus_window(title: str) -> Tuple[bool, str]:
    if not PYGETWINDOW:
        return False, "pygetwindow not installed"
    try:
        wins = gw.getWindowsWithTitle(title)
        if wins:
            w = wins[0]
            if w.isMinimized:
                w.restore()
            w.activate()
            time.sleep(0.3)
            return True, f"'{title}' focused"
        return False, f"'{title}' window nahi mila"
    except Exception as e:
        return False, f"Focus error: {e}"


def _list_windows() -> Tuple[bool, str]:
    if PYGETWINDOW:
        try:
            wins = [w.title for w in gw.getAllWindows() if w.title.strip()]
            return True, "Windows: " + ", ".join(wins[:20])
        except Exception:
            pass
    apps = get_running_apps()
    return True, "Running: " + ", ".join(apps)


def _minimize_win(title: str) -> Tuple[bool, str]:
    if not PYGETWINDOW:
        return _hotkey("win", "down")
    try:
        wins = gw.getWindowsWithTitle(title)
        if wins:
            wins[0].minimize()
            return True, f"Minimized: {title}"
        return False, f"'{title}' nahi mila"
    except Exception as e:
        return False, f"Minimize error: {e}"


def _maximize_win(title: str) -> Tuple[bool, str]:
    if not PYGETWINDOW:
        return _hotkey("win", "up")
    try:
        wins = gw.getWindowsWithTitle(title)
        if wins:
            w = wins[0]
            if w.isMinimized:
                w.restore()
            w.maximize()
            return True, f"Maximized: {title}"
        return False, f"'{title}' nahi mila"
    except Exception as e:
        return False, f"Maximize error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL APP CONTROLLER (screen-vision based — works on ANY app)
# ══════════════════════════════════════════════════════════════════════════════
_UI_CTRL = UniversalAppController()   # Shared instance, KB set later


# ══════════════════════════════════════════════════════════════════════════════
# MAIN AUTOMATION CLASS
# ══════════════════════════════════════════════════════════════════════════════
class Automation:
    def __init__(self, settings: dict):
        self.settings   = settings
        self._brain     = None
        self._home_ctrl = HomeAutomationController(settings)

    def _set_kb(self, kb):
        _UI_CTRL.kb = kb

    # ── Core execute ─────────────────────────────────────────────────────
    def execute(self, action: dict) -> Tuple[bool, str]:
        a      = action.get("action", "").lower().strip()
        target = str(action.get("target", "")).strip()
        delay  = float(action.get("delay", action.get("_delay", 0)) or 0)

        if delay > 0:
            time.sleep(delay)

        # ── APP LAUNCH / CONTROL ─────────────────────────────────────────
        if a == "open_app":
            return launch_app(target)

        if a == "close_app":
            return close_app_by_name(target)

        if a == "minimize_app":
            return _minimize_win(target)

        if a == "maximize_app":
            return _maximize_win(target)

        if a == "focus_window":
            return _focus_window(target)

        if a == "list_windows":
            return _list_windows()

        if a == "list_installed_apps":
            apps = get_running_apps()
            return True, "Running apps: " + ", ".join(apps[:20])

        if a == "scan_all_apps":
            # Full scan — returns what's installed
            found = get_all_installed_apps()
            names = list(found.keys())[:30]
            return True, f"Found {len(found)} apps: {', '.join(names)}"

        # ── UNIVERSAL UI CONTROL (works on ANY app) ───────────────────────
        if a == "click_ui":
            # Click any UI element by text/intent in current app
            return click_ui_element(target)

        if a == "click_menu":
            # Navigate menu: "File > Export > Export as MP4"
            return _UI_CTRL.do_action_in_current_app(target)

        if a == "do_in_app":
            # Generic: do anything in current app using screen vision
            # target = "click Export button" or "type in search field" etc.
            return _UI_CTRL.do_action_in_current_app(target)

        if a == "find_and_type":
            # target = "field_name|text_to_type"
            parts = target.split("|", 1)
            field = parts[0].strip()
            text  = parts[1].strip() if len(parts) > 1 else ""
            return find_and_type(field, text)

        if a == "read_ui":
            # Dump all visible UI elements for AI context
            ui_text = list_all_ui_elements_text()
            return True, f"UI elements:\n{ui_text[:600]}"

        if a == "app_shortcut":
            # Universal: infer shortcut from description
            keys = _UI_CTRL._infer_shortcut(target)
            if keys:
                return _hotkey(*keys)
            # Fall through to click_ui
            return click_ui_element(target)

        if a == "app_action":
            # Combined: try shortcut first, then click, then menu
            keys = _UI_CTRL._infer_shortcut(target)
            if keys:
                ok, msg = _hotkey(*keys)
                if ok:
                    return ok, f"App action '{target}': {msg}"
            return _UI_CTRL.do_action_in_current_app(target)

        # ── WEB / BROWSER ────────────────────────────────────────────────
        if a == "open_url":
            url = target
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            return _open_in_best_browser(url)

        if a == "open_browser":
            return _open_in_best_browser(target or "https://google.com")

        if a == "search_web":
            return _search_web(target)

        if a == "search_youtube":
            return _search_youtube(target)

        if a == "click_first_video":
            return _click_first_video()

        if a == "play_music":
            return _play_music(target)

        if a == "browser_back":
            return _hotkey("alt", "left")

        if a == "browser_refresh":
            return _hotkey("f5")

        if a == "browser_new_tab":
            return _hotkey("ctrl", "t")

        if a == "browser_close_tab":
            return _hotkey("ctrl", "w")

        if a == "fill_form":
            # target = "field_name|value"
            parts = target.split("|", 1)
            field = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""
            return find_and_type(field, value)

        # ── KEYBOARD / MOUSE ────────────────────────────────────────────
        if a == "type_text":
            return _type_text(target)

        if a == "hotkey":
            keys = [k.strip() for k in re.split(r'[+,\s]+', target) if k.strip()]
            return _hotkey(*keys) if keys else (False, "No keys")

        if a == "press_key":
            return _press_key(target)

        if a == "clear_field":
            if _pag:
                _pag.hotkey("ctrl", "a")
                _pag.press("delete")
            return True, "Field cleared"

        if a == "mouse_click":
            if not _pag:
                return False, "pyautogui not installed"
            x, y = _parse_coords(target)
            if x and y:
                _pag.click(x, y)
                return True, f"Clicked ({x},{y})"
            _pag.click()
            return True, "Clicked"

        if a == "double_click":
            if not _pag:
                return False, "pyautogui not installed"
            x, y = _parse_coords(target)
            _pag.doubleClick(x, y) if (x and y) else _pag.doubleClick()
            return True, f"Double-clicked"

        if a == "right_click":
            if not _pag:
                return False, "pyautogui not installed"
            x, y = _parse_coords(target)
            _pag.rightClick(x, y) if (x and y) else _pag.rightClick()
            return True, "Right-clicked"

        if a == "mouse_move":
            if not _pag:
                return False, "pyautogui not installed"
            x, y = _parse_coords(target)
            if x and y:
                _pag.moveTo(x, y, duration=0.3)
                return True, f"Moved to ({x},{y})"
            return False, "Coordinates chahiye"

        if a in ("mouse_scroll_up", "scroll_up"):
            return _scroll("up")

        if a in ("mouse_scroll_down", "scroll_down"):
            return _scroll("down")

        if a == "drag_to":
            nums = re.findall(r'\d+', target)
            if len(nums) >= 4 and _pag:
                _pag.moveTo(int(nums[0]), int(nums[1]))
                _pag.dragTo(int(nums[2]), int(nums[3]), duration=0.5)
                return True, f"Dragged ({nums[0]},{nums[1]})→({nums[2]},{nums[3]})"
            return False, "drag_to needs 4 numbers"

        # ── SCREEN ──────────────────────────────────────────────────────
        if a == "screenshot":
            return _screenshot()

        if a == "read_screen":
            text = read_screen_and_describe()
            return bool(text), text[:800]

        if a == "find_and_click":
            return click_ui_element(target)

        if a == "find_text_on_screen":
            ok, msg = click_ui_element(target, double=False)
            return ok, msg

        # ── SYSTEM ──────────────────────────────────────────────────────
        if a == "volume_up":
            return _volume_up()

        if a == "volume_down":
            return _volume_down()

        if a == "mute":
            return _mute()

        if a == "lock_screen":
            return _lock_screen()

        if a == "system_info":
            return _system_info()

        if a == "list_processes":
            if PSUTIL:
                procs = {p.info["name"]
                         for p in psutil.process_iter(["name"])
                         if p.info.get("name")}
                return True, "Running: " + ", ".join(list(procs)[:25])
            return False, "psutil not installed"

        if a == "kill_process":
            if PSUTIL:
                killed = []
                for proc in psutil.process_iter(["name", "pid"]):
                    if target.lower() in proc.info.get("name", "").lower():
                        proc.kill()
                        killed.append(proc.info["name"])
                if killed:
                    return True, f"Killed: {', '.join(killed)}"
                return False, f"'{target}' nahi mila"
            return close_app_by_name(target)

        # ── FILES ───────────────────────────────────────────────────────
        if a == "open_file":
            try:
                os.startfile(target)
                return True, f"File opened: {Path(target).name}"
            except Exception as e:
                return False, f"Open file error: {e}"

        if a == "save_file":
            return _hotkey("ctrl", "s")

        if a == "save_as":
            ok, msg = _hotkey("ctrl", "shift", "s")
            if ok and target and _pag:
                time.sleep(0.7)
                _pag.write(target, interval=0.02)
                _pag.press("enter")
            return ok, msg

        if a == "new_file":
            return _hotkey("ctrl", "n")

        # ── USB STORAGE ─────────────────────────────────────────────────
        if a == "list_usb_drives":
            return _list_usb_drives()

        if a == "list_usb_files":
            return _list_usb_files(target)

        if a == "open_usb_file":
            return _open_usb_file(target)

        # ── USB SERIAL DEVICES ──────────────────────────────────────────
        if a == "list_serial_devices":
            return list_connected_serial_devices()

        if a == "serial_send":
            # target = "PORT|command|baud" or just "command"
            parts  = target.split("|")
            port   = parts[0].strip() if len(parts) >= 3 else ""
            cmd    = parts[1].strip() if len(parts) >= 3 else parts[0].strip()
            baud   = int(parts[2]) if len(parts) >= 3 and parts[2].strip().isdigit() else 9600
            if not port:
                # Auto-detect first device
                devices = scan_serial_ports()
                port = devices[0].port if devices else ""
            return send_serial_command(port, cmd, baud)

        # ── FIRMWARE UPLOAD (ANY board) ──────────────────────────────────
        if a in ("upload_firmware", "upload_code", "upload_to_board", "upload_arduino"):
            # target = "sketch_path|board|port" or "board|port"
            parts       = target.split("|")
            sketch_path = ""
            board       = "arduino uno"
            port        = ""
            code        = action.get("code", "")  # Optional inline code

            if len(parts) == 1:
                # Just board name
                board = parts[0].strip() or "arduino uno"
            elif len(parts) == 2:
                sketch_path = parts[0].strip()
                board       = parts[1].strip()
            elif len(parts) >= 3:
                sketch_path = parts[0].strip()
                board       = parts[1].strip()
                port        = parts[2].strip()

            return upload_to_board(
                sketch_path=sketch_path,
                sketch_code=code,
                board=board,
                port=port,
                libraries=action.get("libraries", [])
            )

        # ── HOME AUTOMATION via USB SERIAL ───────────────────────────────
        # NO ALEXA. Pure USB serial relay board control.
        if a in ("home_control", "smart_home", "relay_control",
                 "home_automation", "light_control", "fan_control"):
            return self._home_ctrl.control(target)

        if a == "home_custom":
            # target = "PORT|command|baud"
            parts = target.split("|")
            port  = parts[0].strip() if len(parts) >= 2 else ""
            cmd   = parts[1].strip() if len(parts) >= 2 else target
            baud  = int(parts[2]) if len(parts) >= 3 and parts[2].strip().isdigit() else 9600
            return self._home_ctrl.send_custom(port, cmd, baud)

        if a == "home_status":
            return True, self._home_ctrl.get_status()

        # ── CODE EXECUTION ───────────────────────────────────────────────
        if a == "run_python":
            return _run_python(target)

        if a == "run_command":
            return _run_command(target)

        # ── KNOWLEDGE / RESEARCH ─────────────────────────────────────────
        if a == "research_app":
            if self._brain and hasattr(self._brain, "researcher"):
                result = self._brain.researcher.research_app(target)
                if result:
                    self._brain.kb.save_app_info(target, "", ui_notes=result[:1000])
                    return True, f"App research done & saved: {target}"
            return True, f"Research triggered for: {target}"

        if a == "learn_and_save":
            if self._brain and hasattr(self._brain, "kb"):
                self._brain.kb.cache_research(target, f"Learned: {target}")
                return True, f"Knowledge saved: {target[:60]}"
            return True, "Knowledge noted"

        if a == "recall":
            if self._brain and hasattr(self._brain, "kb"):
                r = self._brain.kb.recall_task(target)
                return True, r or f"'{target}' ka koi record nahi"
            return False, "KB unavailable"

        # ── WAIT / DELAY ─────────────────────────────────────────────────
        if a == "wait":
            secs = float(re.search(r'\d+(\.\d+)?', target).group()) if re.search(r'\d+', target) else 1.0
            time.sleep(min(secs, 30.0))
            return True, f"Waited {secs}s"

        # ── RESIZE WINDOW ────────────────────────────────────────────────
        if a == "resize_window":
            nums = re.findall(r'\d+', target)
            if len(nums) >= 2 and PYGETWINDOW:
                try:
                    wins = gw.getAllWindows()
                    if wins:
                        wins[0].resizeTo(int(nums[0]), int(nums[1]))
                        return True, f"Resized to {nums[0]}x{nums[1]}"
                except Exception as e:
                    return False, f"Resize error: {e}"
            return False, "Resize: need w,h and pygetwindow"

        # ── UNKNOWN ──────────────────────────────────────────────────────
        return False, (
            f"Unknown action: '{a}'. "
            f"Common actions: open_app, do_in_app, click_ui, type_text, "
            f"search_web, screenshot, serial_send, upload_firmware, home_control"
        )

    def execute_chain(self, actions: List[dict]) -> List[Tuple[bool, str]]:
        """Execute ordered list of actions with per-action delays."""
        results = []
        for i, act in enumerate(actions):
            print(f"[AUTO] Step {i+1}/{len(actions)}: {act.get('action')}")
            ok, msg = self.execute(act)
            results.append((ok, msg))
            # Default inter-step gap
            gap = float(act.get("_delay", act.get("delay", 0.3)) or 0.3)
            if gap > 0:
                time.sleep(gap)
        return results

