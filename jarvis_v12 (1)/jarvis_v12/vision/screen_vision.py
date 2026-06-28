"""
vision/screen_vision.py — JARVIS OMEGA V10
Screen reading via OCR (pytesseract / easyocr) + Ollama vision model.
No API keys required — 100% local.
"""
from __future__ import annotations

import os
import re
import time
import base64
import tempfile
from pathlib import Path
from typing import Optional, Tuple

BASE = Path(__file__).resolve().parent.parent

# ── Screenshot ─────────────────────────────────────────────────────────────
try:
    import mss
    MSS = True
except ImportError:
    MSS = False

try:
    from PIL import Image, ImageGrab
    PIL = True
except ImportError:
    PIL = False

# ── OCR ────────────────────────────────────────────────────────────────────
try:
    import pytesseract
    TESSERACT = True
except ImportError:
    TESSERACT = False

try:
    import easyocr
    EASYOCR = True
except ImportError:
    EASYOCR = False

# ── PyAutoGUI ──────────────────────────────────────────────────────────────
try:
    import pyautogui
    PYAUTOGUI = True
except ImportError:
    PYAUTOGUI = False

# ── Requests (for Ollama vision) ───────────────────────────────────────────
try:
    import requests
    REQ = True
except ImportError:
    REQ = False

_easyocr_reader = None


def _get_easyocr():
    global _easyocr_reader
    if _easyocr_reader is None and EASYOCR:
        try:
            _easyocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception as e:
            print(f"[VISION] EasyOCR init error: {e}")
    return _easyocr_reader


class ScreenReader:
    def __init__(self, settings: dict):
        self.settings = settings
        self.ollama_url = settings.get("ollama_url", "http://localhost:11434")
        self.vision_model = settings.get("V10_MODELS", {}).get("vision", "qwen3-vl:2b")

    def screenshot(self, save_to_disk: bool = False) -> Optional[str]:
        """
        Take a screenshot.
        V12 FIX: save_to_disk=False by default for background OCR reads —
        avoids flooding data/screenshots/ every 3 seconds.
        Only saves to disk when user explicitly requests a screenshot.
        Returns path if saved, or a temp path, or None.
        """
        if save_to_disk:
            shots_dir = BASE / "data" / "screenshots"
            shots_dir.mkdir(parents=True, exist_ok=True)
            ts   = time.strftime("%Y%m%d_%H%M%S")
            path = str(shots_dir / f"screen_{ts}.png")
        else:
            import tempfile
            path = tempfile.mktemp(suffix=".png", prefix="jarvis_ocr_")

        # Try mss first (fastest)
        if MSS:
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]  # Primary monitor
                    sct_img = sct.grab(monitor)
                    if PIL:
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        img.save(path)
                    else:
                        mss.tools.to_png(sct_img.rgb, sct_img.size, output=path)
                if save_to_disk:
                    print(f"[VISION] Screenshot saved: {path}")
                return path
            except Exception as e:
                print(f"[VISION] mss error: {e}")

        # PIL fallback
        if PIL:
            try:
                img = ImageGrab.grab()
                img.save(path)
                if save_to_disk:
                    print(f"[VISION] Screenshot saved (PIL): {path}")
                return path
            except Exception as e:
                print(f"[VISION] PIL error: {e}")

        # pyautogui fallback
        if PYAUTOGUI:
            try:
                img = pyautogui.screenshot()
                img.save(path)
                if save_to_disk:
                    print(f"[VISION] Screenshot saved (pyautogui): {path}")
                return path
            except Exception as e:
                print(f"[VISION] pyautogui error: {e}")

        return None

    def read_ocr(self, image_path: str = None) -> str:
        """Extract text from screen using OCR."""
        if not image_path:
            image_path = self.screenshot()
        if not image_path:
            return "[Screenshot failed]"

        # Try pytesseract first
        if TESSERACT and PIL:
            try:
                img = Image.open(image_path)
                text = pytesseract.image_to_string(img, lang='eng')
                if text.strip():
                    return text.strip()
            except Exception as e:
                print(f"[VISION] Tesseract error: {e}")

        # EasyOCR fallback
        reader = _get_easyocr()
        if reader:
            try:
                results = reader.readtext(image_path)
                text = " ".join([r[1] for r in results])
                if text.strip():
                    return text.strip()
            except Exception as e:
                print(f"[VISION] EasyOCR error: {e}")

        return "[OCR failed — install pytesseract or easyocr]"

    def read_with_vision_model(self, image_path: str) -> str:
        """Send screenshot to Ollama vision model for understanding."""
        if not REQ:
            return ""
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            body = {
                "model": self.vision_model,
                "messages": [{
                    "role": "user",
                    "content": "Describe what you see on this screen. List all visible text, buttons, windows, and important UI elements. Be concise.",
                    "images": [img_b64]
                }],
                "stream": False,
                "options": {"num_predict": 400, "temperature": 0.1}
            }
            r = requests.post(f"{self.ollama_url}/api/chat", json=body, timeout=(3, 20))
            if r.status_code == 200:
                return r.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"[VISION] Vision model error: {e}")
        return ""

    def read(self, use_ai: bool = True) -> str:
        """Read screen — OCR + optional AI description."""
        # V12: save_to_disk=False for background reads (no disk flood)
        path = self.screenshot(save_to_disk=use_ai)
        if not path:
            return "[Screen read failed]"

        # OCR text
        ocr_text = self.read_ocr(path)

        # Vision AI description
        if use_ai:
            ai_desc = self.read_with_vision_model(path)
            if ai_desc:
                return f"[Screen OCR]\n{ocr_text}\n\n[AI Vision Description]\n{ai_desc}"

        return ocr_text

    def find_and_click(self, target_text: str) -> Tuple[bool, str]:
        """Find text on screen via OCR and click it."""
        if not PYAUTOGUI:
            return False, "pyautogui not installed"

        try:
            # Take screenshot
            if PIL:
                screen = ImageGrab.grab()
            elif MSS:
                with mss.mss() as sct:
                    sct_img = sct.grab(sct.monitors[0])
                    screen = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            else:
                return False, "PIL/mss not available"

            # OCR with location
            if TESSERACT:
                data = pytesseract.image_to_data(
                    screen, output_type=pytesseract.Output.DICT)
                target_lower = target_text.lower()
                for i, word in enumerate(data['text']):
                    if target_lower in word.lower() and int(data['conf'][i]) > 50:
                        x = data['left'][i] + data['width'][i] // 2
                        y = data['top'][i] + data['height'][i] // 2
                        pyautogui.click(x, y)
                        return True, f"Clicked '{word}' at ({x}, {y})"

            # EasyOCR fallback with location
            reader = _get_easyocr()
            if reader:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    tmp = f.name
                screen.save(tmp)
                results = reader.readtext(tmp)
                os.unlink(tmp)
                for bbox, word, conf in results:
                    if target_text.lower() in word.lower() and conf > 0.5:
                        # bbox is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                        cx = int((bbox[0][0] + bbox[2][0]) / 2)
                        cy = int((bbox[0][1] + bbox[2][1]) / 2)
                        pyautogui.click(cx, cy)
                        return True, f"Clicked '{word}' at ({cx}, {cy})"

            return False, f"'{target_text}' not found on screen"
        except Exception as e:
            return False, f"find_and_click error: {e}"


_reader_instance: Optional[ScreenReader] = None


def get_screen_reader(settings: dict) -> ScreenReader:
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = ScreenReader(settings)
    return _reader_instance
