"""
tools/universal_controller.py — JARVIS V12

THE UNIVERSAL APP CONTROLLER
"If a human can see it and click it, JARVIS can too."

Core idea:
  1. Take a screenshot
  2. OCR → find ALL text/buttons/UI elements on screen
  3. AI maps user intent to a UI element (no hardcoded shortcuts)
  4. Click / type / navigate
  5. Take screenshot again to verify result
  6. Learn the UI layout and save to knowledge base for next time

This replaces all hardcoded shortcuts. Works on:
  - Any video editor (DaVinci, Premiere, Shotcut, Kdenlive, OpenShot, CapCut...)
  - Any game engine (Godot, Unity, Unreal, GDevelop, RPGMaker...)
  - Any IDE (VS Code, Arduino IDE, PyCharm, IntelliJ, Eclipse, Android Studio...)
  - Any browser
  - Any Office app
  - ANY app at all — if it's visible on screen, JARVIS can interact with it
"""
from __future__ import annotations

import os, re, time, json, threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent

# ── Optional deps ─────────────────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    PYAUTOGUI = True
except ImportError:
    PYAUTOGUI = False

try:
    from PIL import Image, ImageGrab, ImageFilter, ImageEnhance
    PIL = True
except ImportError:
    PIL = False

try:
    import pytesseract
    # Common Tesseract install paths on Windows
    for _tp in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]:
        if os.path.exists(_tp):
            pytesseract.pytesseract.tesseract_cmd = _tp
            break
    TESSERACT = True
except ImportError:
    TESSERACT = False

try:
    import mss
    MSS = True
except ImportError:
    MSS = False

try:
    import cv2, numpy as np
    CV2 = True
except ImportError:
    CV2 = False

try:
    import requests
    REQ = True
except ImportError:
    REQ = False

try:
    import ctypes
    CTYPES = True
except Exception:
    CTYPES = False


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN CAPTURE (best available method)
# ══════════════════════════════════════════════════════════════════════════════
def capture_screen(region=None) -> Optional["Image.Image"]:
    """Capture screen. Returns PIL Image or None."""
    try:
        if MSS:
            import mss as _mss
            with _mss.mss() as sct:
                if region:
                    mon = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
                else:
                    mon = sct.monitors[1]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                return img
        elif PIL:
            if region:
                return ImageGrab.grab(bbox=region)
            return ImageGrab.grab()
    except Exception as e:
        print(f"[SCREEN] Capture error: {e}")
    return None


def screen_size() -> Tuple[int, int]:
    if PYAUTOGUI:
        return pyautogui.size()
    if CTYPES:
        return (
            ctypes.windll.user32.GetSystemMetrics(0),
            ctypes.windll.user32.GetSystemMetrics(1)
        )
    return (1920, 1080)


# ══════════════════════════════════════════════════════════════════════════════
# OCR ENGINE — extract text AND positions from screen
# ══════════════════════════════════════════════════════════════════════════════
class UIElement:
    """Represents a found UI element (text + position)."""
    def __init__(self, text: str, x: int, y: int, w: int = 0, h: int = 0,
                 confidence: float = 0.0):
        self.text       = text.strip()
        self.x          = x
        self.y          = y
        self.w          = w
        self.h          = h
        self.cx         = x + w // 2   # center x
        self.cy         = y + h // 2   # center y
        self.confidence = confidence

    def __repr__(self):
        return f"UIElement('{self.text}' @({self.cx},{self.cy}))"


def get_all_ui_elements(image=None, region=None) -> List[UIElement]:
    """
    OCR the screen and return ALL visible text elements with their positions.
    This is how JARVIS 'sees' the app UI.
    """
    if not TESSERACT:
        return []
    try:
        if image is None:
            image = capture_screen(region)
        if image is None:
            return []

        # Enhance image for better OCR
        if PIL:
            # Upscale for small text
            w, h = image.size
            if w < 1920:
                image = image.resize((w * 2, h * 2), Image.LANCZOS)
            # Increase contrast
            image = ImageEnhance.Contrast(image).enhance(1.5)

        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 11 --oem 3"  # Sparse text mode
        )

        elements: List[UIElement] = []
        scale = 0.5 if (image.size[0] > 1920) else 1.0

        for i, text in enumerate(data["text"]):
            text = text.strip()
            if not text or len(text) < 1:
                continue
            conf = int(data["conf"][i])
            if conf < 20:  # Skip very low confidence
                continue
            x = int(data["left"][i]  * scale)
            y = int(data["top"][i]   * scale)
            w = int(data["width"][i] * scale)
            h = int(data["height"][i]* scale)
            elements.append(UIElement(text, x, y, w, h, conf / 100.0))

        return elements

    except Exception as e:
        print(f"[OCR] Error: {e}")
        return []


def get_full_screen_text(image=None) -> str:
    """Get all text from screen as a flat string."""
    if not TESSERACT:
        return ""
    try:
        if image is None:
            image = capture_screen()
        if image is None:
            return ""
        return pytesseract.image_to_string(image, config="--psm 6")
    except Exception as e:
        print(f"[OCR] Full text error: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# SMART UI FINDER — finds UI elements by fuzzy intent matching
# ══════════════════════════════════════════════════════════════════════════════
class SmartUIFinder:
    """
    Given a user intent like "click Export button" or "find File menu",
    scans the screen and returns the best-matching UI element to click.
    No hardcoded coordinates. No hardcoded app names.
    """

    def find(self, intent: str, image=None,
             threshold: float = 0.3) -> Optional[UIElement]:
        """
        Find best UI element matching intent.
        Returns UIElement if found, None otherwise.
        """
        elements = get_all_ui_elements(image)
        if not elements:
            return None

        intent_words = set(re.findall(r'\w+', intent.lower()))
        best: Optional[UIElement] = None
        best_score = 0.0

        for el in elements:
            el_words = set(re.findall(r'\w+', el.text.lower()))
            if not el_words:
                continue

            # Exact substring match → highest score
            if intent.lower() in el.text.lower() or el.text.lower() in intent.lower():
                score = 1.0
            else:
                # Jaccard similarity
                intersection = intent_words & el_words
                union        = intent_words | el_words
                score = len(intersection) / max(len(union), 1)

            # Boost score for common UI keywords
            ui_keywords = {"file", "edit", "view", "tools", "export", "import",
                           "save", "open", "new", "close", "help", "settings",
                           "preferences", "render", "build", "run", "debug",
                           "play", "stop", "pause", "cut", "copy", "paste",
                           "undo", "redo", "zoom", "format", "insert", "ok",
                           "cancel", "apply", "yes", "no", "next", "back",
                           "submit", "search", "upload", "download", "add",
                           "delete", "remove", "create", "start", "finish"}
            if el_words & ui_keywords:
                score *= 1.2

            # Confidence boost
            score *= (0.7 + 0.3 * el.confidence)

            if score > best_score and score >= threshold:
                best_score = score
                best        = el

        return best

    def find_all_matching(self, intent: str, image=None,
                          threshold: float = 0.25,
                          max_results: int = 5) -> List[UIElement]:
        """Find all elements matching intent, sorted by score."""
        elements = get_all_ui_elements(image)
        if not elements:
            return []

        intent_words = set(re.findall(r'\w+', intent.lower()))
        scored: List[Tuple[float, UIElement]] = []

        for el in elements:
            el_words = set(re.findall(r'\w+', el.text.lower()))
            if not el_words:
                continue
            if intent.lower() in el.text.lower():
                score = 1.0
            else:
                intersection = intent_words & el_words
                union        = intent_words | el_words
                score = len(intersection) / max(len(union), 1)
            if score >= threshold:
                scored.append((score, el))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [el for _, el in scored[:max_results]]

    def dump_all_text(self, image=None) -> str:
        """Dump all visible text for AI context."""
        elements = get_all_ui_elements(image)
        return " | ".join(f"[{el.text}]" for el in elements if el.text)


# Global finder instance
_FINDER = SmartUIFinder()


# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL CLICKER — clicks any visible UI element by text/intent
# ══════════════════════════════════════════════════════════════════════════════
def click_ui_element(intent: str, double: bool = False,
                     right: bool = False,
                     region=None, wait_after: float = 0.4,
                     retries: int = 2) -> Tuple[bool, str]:
    """
    Universal click: finds text/button on screen and clicks it.
    Works on ANY app — no hardcoded coords or app-specific logic.
    """
    if not PYAUTOGUI:
        return False, "pyautogui not installed — pip install pyautogui"

    for attempt in range(retries + 1):
        image = capture_screen(region)
        el    = _FINDER.find(intent, image)

        if el:
            if double:
                pyautogui.doubleClick(el.cx, el.cy)
            elif right:
                pyautogui.rightClick(el.cx, el.cy)
            else:
                pyautogui.moveTo(el.cx, el.cy, duration=0.25)
                pyautogui.click()

            time.sleep(wait_after)
            return True, f"Clicked '{el.text}' at ({el.cx},{el.cy})"

        if attempt < retries:
            time.sleep(0.8)   # Wait for UI to load and retry

    return False, f"'{intent}' screen pe nahi mila — UI visible hai?"


def find_and_type(field_intent: str, text_to_type: str,
                  clear_first: bool = True,
                  region=None) -> Tuple[bool, str]:
    """Find a text field and type into it."""
    ok, msg = click_ui_element(field_intent, region=region)
    if ok:
        time.sleep(0.3)
        if clear_first:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("delete")
            time.sleep(0.1)
        pyautogui.write(text_to_type, interval=0.025)
        return True, f"Typed '{text_to_type[:40]}' into '{field_intent}'"
    return False, f"Field '{field_intent}' nahi mila: {msg}"


def read_screen_and_describe() -> str:
    """Take screenshot and return all visible text + window context."""
    try:
        image = capture_screen()
        text  = get_full_screen_text(image)
        active = _get_active_window()
        result = []
        if active:
            result.append(f"Active: {active}")
        if text:
            result.append(f"Screen text: {text[:1000]}")
        return "\n".join(result)
    except Exception as e:
        return f"Screen read error: {e}"


def _get_active_window() -> str:
    if not CTYPES:
        return ""
    try:
        hwnd   = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf    = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def list_all_ui_elements_text() -> str:
    """List all UI elements currently visible — for AI to decide what to click."""
    image    = capture_screen()
    elements = get_all_ui_elements(image)
    if not elements:
        return "No UI elements detected"
    # Group by rough Y position (rows)
    rows: Dict[int, List[str]] = {}
    for el in elements:
        row_key = (el.cy // 30) * 30
        rows.setdefault(row_key, []).append(el.text)
    lines = []
    for y in sorted(rows.keys()):
        lines.append(" | ".join(rows[y]))
    return "\n".join(lines[:40])  # First 40 rows


# ══════════════════════════════════════════════════════════════════════════════
# ACTIVE WINDOW APP CONTROLLER
# Works on ANY open application using screen vision
# ══════════════════════════════════════════════════════════════════════════════
class UniversalAppController:
    """
    Controls any application visible on screen.
    Steps:
      1. Scan screen for UI elements
      2. Match user intent to element
      3. Click / interact
      4. Verify result with another screenshot
      5. Save learned UI to knowledge base
    """

    def __init__(self, knowledge_base=None):
        self.kb     = knowledge_base
        self._cache: Dict[str, Any] = {}  # app_name → ui_map

    def do_action_in_current_app(self, action_description: str,
                                  target_text: str = "") -> Tuple[bool, str]:
        """
        Perform any action in the currently active application.
        action_description: natural language e.g. "click Export button"
        target_text:        optional text to type after clicking
        """
        # Get current app name for context
        current_app = _get_active_window()
        print(f"[UICTRL] Action: '{action_description}' | App: '{current_app}'")

        # First: try clicking the intent directly
        ok, msg = click_ui_element(action_description)
        if ok:
            if target_text:
                time.sleep(0.4)
                pyautogui.write(target_text, interval=0.02)
            # Save to KB
            if self.kb and current_app:
                self._learn_ui_action(current_app, action_description, msg)
            return True, f"{action_description} → {msg}"

        # Second: try menu navigation (File > Export, Edit > Preferences, etc.)
        if " > " in action_description or " → " in action_description:
            return self._navigate_menu(action_description)

        # Third: scan all visible elements and pick best
        elements = _FINDER.find_all_matching(action_description)
        if elements:
            best = elements[0]
            pyautogui.moveTo(best.cx, best.cy, duration=0.3)
            pyautogui.click()
            time.sleep(0.4)
            if target_text:
                pyautogui.write(target_text, interval=0.02)
            return True, f"Clicked best match: '{best.text}'"

        # Fourth: try keyboard shortcut inference
        shortcut = self._infer_shortcut(action_description)
        if shortcut:
            pyautogui.hotkey(*shortcut)
            return True, f"Used shortcut {'+'.join(shortcut)} for '{action_description}'"

        return False, (
            f"'{action_description}' screen pe nahi mila. "
            f"App ke UI mein yeh option visible hai? Main screen scan kar raha hoon:\n"
            f"{list_all_ui_elements_text()[:300]}"
        )

    def _navigate_menu(self, menu_path: str) -> Tuple[bool, str]:
        """
        Navigate multi-level menus: 'File > Export > Export as MP4'
        """
        parts = re.split(r'\s*[>→/]\s*', menu_path)
        for i, part in enumerate(parts):
            ok, msg = click_ui_element(part.strip(), wait_after=0.6)
            if not ok:
                return False, f"Menu item '{part}' nahi mila (step {i+1})"
            time.sleep(0.5)
        return True, f"Menu navigated: {menu_path}"

    def _infer_shortcut(self, description: str) -> Optional[List[str]]:
        """
        Infer universal keyboard shortcuts from action description.
        These work across ALL apps (Windows standard shortcuts).
        """
        d = description.lower()
        # Universal Windows shortcuts
        if any(w in d for w in ["save",    "save file"]):         return ["ctrl", "s"]
        if any(w in d for w in ["save as"]):                      return ["ctrl", "shift", "s"]
        if any(w in d for w in ["new",     "new file"]):          return ["ctrl", "n"]
        if any(w in d for w in ["open",    "open file"]):         return ["ctrl", "o"]
        if any(w in d for w in ["close",   "close file"]):        return ["ctrl", "w"]
        if any(w in d for w in ["undo"]):                         return ["ctrl", "z"]
        if any(w in d for w in ["redo"]):                         return ["ctrl", "y"]
        if any(w in d for w in ["copy"]):                         return ["ctrl", "c"]
        if any(w in d for w in ["paste"]):                        return ["ctrl", "v"]
        if any(w in d for w in ["cut"]):                          return ["ctrl", "x"]
        if any(w in d for w in ["select all"]):                   return ["ctrl", "a"]
        if any(w in d for w in ["find",    "search in"]):         return ["ctrl", "f"]
        if any(w in d for w in ["replace"]):                      return ["ctrl", "h"]
        if any(w in d for w in ["print"]):                        return ["ctrl", "p"]
        if any(w in d for w in ["zoom in",  "zoom+"]):            return ["ctrl", "="]
        if any(w in d for w in ["zoom out", "zoom-"]):            return ["ctrl", "-"]
        if any(w in d for w in ["full screen", "fullscreen"]):    return ["f11"]
        if any(w in d for w in ["refresh",  "reload"]):           return ["f5"]
        if any(w in d for w in ["properties"]):                   return ["alt", "enter"]
        if any(w in d for w in ["task manager"]):                 return ["ctrl", "shift", "esc"]
        if any(w in d for w in ["switch window",  "alt tab"]):    return ["alt", "tab"]
        if any(w in d for w in ["minimize"]):                     return ["win", "down"]
        if any(w in d for w in ["maximize"]):                     return ["win", "up"]
        if any(w in d for w in ["snap left"]):                    return ["win", "left"]
        if any(w in d for w in ["snap right"]):                   return ["win", "right"]
        if any(w in d for w in ["run",      "execute"]):          return ["f5"]
        if any(w in d for w in ["stop",     "terminate"]):        return ["f9"]
        if any(w in d for w in ["build",    "compile"]):          return ["ctrl", "b"]
        if any(w in d for w in ["debug"]):                        return ["f8"]
        if any(w in d for w in ["next tab"]):                     return ["ctrl", "tab"]
        if any(w in d for w in ["prev tab"]):                     return ["ctrl", "shift", "tab"]
        if any(w in d for w in ["comment"]):                      return ["ctrl", "slash"]
        if any(w in d for w in ["format"]):                       return ["alt", "shift", "f"]
        if any(w in d for w in ["go to line"]):                   return ["ctrl", "g"]
        if any(w in d for w in ["duplicate line"]):               return ["ctrl", "shift", "d"]
        if any(w in d for w in ["delete line"]):                  return ["ctrl", "shift", "k"]
        if any(w in d for w in ["rename"]):                       return ["f2"]
        if any(w in d for w in ["export",   "render", "output"]): return ["ctrl", "e"]
        if any(w in d for w in ["import",   "import file"]):      return ["ctrl", "i"]
        if any(w in d for w in ["play",     "preview"]):          return ["space"]
        if any(w in d for w in ["settings", "preferences"]):      return ["ctrl", ","]
        return None

    def _learn_ui_action(self, app_name: str, action: str, result: str):
        """Save a discovered UI action to knowledge base."""
        if self.kb:
            try:
                note = f"{action} → {result}"
                existing = self.kb.get_app_info(app_name)
                existing_notes = existing.get("ui_notes", "") if existing else ""
                if note not in existing_notes:
                    self.kb.save_app_info(
                        app_name, "", 
                        ui_notes=(existing_notes + "\n" + note)[:1500]
                    )
            except Exception:
                pass

    def get_app_ui_snapshot(self) -> Dict[str, Any]:
        """Return a full snapshot of current app UI for AI analysis."""
        image = capture_screen()
        return {
            "window_title": _get_active_window(),
            "all_text":     get_full_screen_text(image),
            "elements":     [
                {"text": el.text, "x": el.cx, "y": el.cy}
                for el in get_all_ui_elements(image)[:80]
            ]
        }

