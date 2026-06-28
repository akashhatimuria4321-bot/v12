"""
core/brain.py — JARVIS OMEGA V12

V12 FEATURES:
  - Continuous screen-reading context (AI always knows what's on screen)
  - Multi-step task chaining: "open YouTube and play latest song" → open → search → click → play
  - Logical context carry-over: remembers last app opened, last action taken
  - Chrome real-time research: can look up any app's UI, shortcuts, tutorials
  - Knowledge base: saves learnt info to SQLite for instant recall
  - App inventory scan: knows every installed app on the laptop
  - Pendrive detection and file browsing
  - Spotify assumption REMOVED — checks if app is installed first
  - Arduino/ESP32 IDE upload support
  - Home automation stubs (Alexa/Google Home via HTTP)
  - All Ollama models with sequential fallback (no timeout crashes)
"""
from __future__ import annotations

import os, re, json, time, sqlite3, threading, subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent

try:
    import requests
    REQ = True
except ImportError:
    REQ = False
    print("[BRAIN] WARNING: requests not installed — pip install requests")

try:
    from duckduckgo_search import DDGS
    DDG = True
except ImportError:
    DDG = False


# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — persistent learning store
# ═══════════════════════════════════════════════════════════════════════════
class KnowledgeBase:
    """Persistent store: app info, UI layouts, task results, learned facts."""

    def __init__(self):
        db_path = BASE / "data" / "knowledge" / "jarvis_knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_info (
                    app_name TEXT PRIMARY KEY,
                    exe_path TEXT,
                    ui_notes TEXT,
                    shortcuts TEXT,
                    last_used TEXT,
                    is_installed INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS task_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT,
                    result TEXT,
                    app_used TEXT,
                    steps TEXT,
                    ts TEXT
                );
                CREATE TABLE IF NOT EXISTS web_research (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    summary TEXT,
                    source TEXT,
                    ts TEXT
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_msg TEXT,
                    ai_msg TEXT,
                    ts TEXT
                );
                CREATE TABLE IF NOT EXISTS context_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    ts TEXT
                );
            """)
            self.conn.commit()

    # ── App info ───────────────────────────────────────────────────────────
    def save_app_info(self, name: str, exe: str, ui_notes: str = "",
                      shortcuts: str = "", installed: bool = True):
        with self._lock:
            self.conn.execute("""
                INSERT INTO app_info(app_name,exe_path,ui_notes,shortcuts,last_used,is_installed)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(app_name) DO UPDATE SET
                  exe_path=excluded.exe_path,
                  ui_notes=excluded.ui_notes,
                  shortcuts=excluded.shortcuts,
                  last_used=excluded.last_used,
                  is_installed=excluded.is_installed
            """, (name.lower(), exe, ui_notes, shortcuts,
                  datetime.now().isoformat(), int(installed)))
            self.conn.commit()

    def get_app_info(self, name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM app_info WHERE app_name=?", (name.lower(),)
        ).fetchone()
        if row:
            return {"name": row[0], "exe": row[1], "ui_notes": row[2],
                    "shortcuts": row[3], "last_used": row[4], "installed": bool(row[5])}
        return None

    # ── Task memory ────────────────────────────────────────────────────────
    def save_task(self, task: str, result: str, app: str = "", steps: list = None):
        with self._lock:
            self.conn.execute(
                "INSERT INTO task_memory(task,result,app_used,steps,ts) VALUES(?,?,?,?,?)",
                (task, result, app, json.dumps(steps or []), datetime.now().isoformat())
            )
            self.conn.commit()

    def recall_task(self, task_hint: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT result, steps FROM task_memory WHERE task LIKE ? "
            "ORDER BY id DESC LIMIT 1",
            (f"%{task_hint}%",)
        ).fetchone()
        return row[0] if row else None

    # ── Web research cache ─────────────────────────────────────────────────
    def cache_research(self, query: str, summary: str, source: str = ""):
        with self._lock:
            self.conn.execute(
                "INSERT INTO web_research(query,summary,source,ts) VALUES(?,?,?,?)",
                (query, summary, source, datetime.now().isoformat())
            )
            self.conn.commit()

    def recall_research(self, query: str, max_age_hours: float = 24.0) -> Optional[str]:
        row = self.conn.execute(
            "SELECT summary, ts FROM web_research WHERE query LIKE ? "
            "ORDER BY id DESC LIMIT 1",
            (f"%{query[:40]}%",)
        ).fetchone()
        if row:
            try:
                ts = datetime.fromisoformat(row[1])
                age_h = (datetime.now() - ts).total_seconds() / 3600
                if age_h < max_age_hours:
                    return row[0]
            except Exception:
                pass
        return None

    # ── Context state (e.g. last_app_opened, last_url) ───────────────────
    def set_ctx(self, key: str, value: str):
        with self._lock:
            self.conn.execute(
                "INSERT INTO context_state(key,value,ts) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
                (key, value, datetime.now().isoformat())
            )
            self.conn.commit()

    def get_ctx(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM context_state WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    # ── Conversations ──────────────────────────────────────────────────────
    def save_conv(self, user: str, ai: str):
        with self._lock:
            self.conn.execute(
                "INSERT INTO conversations(user_msg,ai_msg,ts) VALUES(?,?,?)",
                (user, ai, datetime.now().isoformat())
            )
            self.conn.execute(
                "DELETE FROM conversations WHERE id NOT IN "
                "(SELECT id FROM conversations ORDER BY id DESC LIMIT 500)"
            )
            self.conn.commit()

    def recent_conv(self, n: int = 10) -> List[dict]:
        rows = self.conn.execute(
            "SELECT user_msg, ai_msg FROM conversations ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [{"user": r[0], "assistant": r[1]} for r in reversed(rows)]


# ═══════════════════════════════════════════════════════════════════════════
# APP SCANNER — finds every installed app on Windows
# ═══════════════════════════════════════════════════════════════════════════
class AppScanner:
    """Scans the Windows system for installed applications."""

    # Common app locations
    SEARCH_ROOTS = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        os.path.expandvars(r"%APPDATA%"),
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    ]

    # Known app name → exe mappings
    KNOWN_APPS = {
        "chrome":        [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
        "firefox":       [r"C:\Program Files\Mozilla Firefox\firefox.exe"],
        "edge":          [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
        "brave":         [r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"],
        "vscode":        [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")],
        "arduino":       [r"C:\Program Files\Arduino IDE\Arduino IDE.exe",
                          r"C:\Program Files (x86)\Arduino\arduino.exe",
                          os.path.expandvars(r"%LOCALAPPDATA%\Programs\arduino-ide\Arduino IDE.exe")],
        "notepad++":     [r"C:\Program Files\Notepad++\notepad++.exe",
                          r"C:\Program Files (x86)\Notepad++\notepad++.exe"],
        "vlc":           [r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                          r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"],
        "davinci resolve": [r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"],
        "kdenlive":      [r"C:\Program Files\kdenlive\bin\kdenlive.exe"],
        "shotcut":       [r"C:\Program Files\Shotcut\shotcut.exe"],
        "premiere":      [os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe Premiere Pro 2024\Adobe Premiere Pro.exe")],
        "after effects": [os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe After Effects 2024\Support Files\AfterFX.exe")],
        "blender":       [r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
                          r"C:\Program Files\Blender Foundation\Blender\blender.exe"],
        "unity":         [os.path.expandvars(r"%PROGRAMFILES%\Unity\Hub\Editor")],
        "godot":         [r"C:\Program Files\Godot\Godot.exe"],
        "unreal":        [os.path.expandvars(r"%PROGRAMFILES%\Epic Games\UE_5.3\Engine\Binaries\Win64\UnrealEditor.exe")],
        "spotify":       [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")],
        "discord":       [os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
                          os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-1.0.9005\Discord.exe")],
        "whatsapp":      [os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe")],
        "telegram":      [os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe")],
        "zoom":          [os.path.expandvars(r"%APPDATA%\Zoom\bin\Zoom.exe")],
        "obs":           [r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"],
        "python":        ["python"],
        "git":           [r"C:\Program Files\Git\bin\git.exe"],
        "steam":         [r"C:\Program Files (x86)\Steam\steam.exe"],
        "notepad":       ["notepad.exe"],
        "calculator":    ["calc.exe"],
        "paint":         ["mspaint.exe"],
        "wordpad":       ["wordpad.exe"],
        "explorer":      ["explorer.exe"],
        "cmd":           ["cmd.exe"],
        "powershell":    ["powershell.exe"],
        "terminal":      ["wt.exe"],
        "taskmgr":       ["taskmgr.exe"],
        "winrar":        [r"C:\Program Files\WinRAR\WinRAR.exe",
                          r"C:\Program Files (x86)\WinRAR\WinRAR.exe"],
        "7zip":          [r"C:\Program Files\7-Zip\7zFM.exe",
                          r"C:\Program Files (x86)\7-Zip\7zFM.exe"],
        "eclipse":       [r"C:\eclipse\eclipse.exe"],
        "intellij":      [os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\IntelliJIdea\bin\idea64.exe")],
        "pycharm":       [os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\PyCharm\bin\pycharm64.exe")],
        "android studio":[os.path.expandvars(r"%LOCALAPPDATA%\Programs\Android Studio\bin\studio64.exe")],
        "word":          [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\WINWORD.EXE")],
        "excel":         [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\EXCEL.EXE")],
        "powerpoint":    [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\POWERPNT.EXE")],
    }

    # Category → recommended free alternatives
    RECOMMENDED = {
        "video_editor": [
            {"name": "DaVinci Resolve", "url": "https://www.blackmagicdesign.com/products/davinciresolve", "why": "Professional, free, best color grading"},
            {"name": "Shotcut",         "url": "https://shotcut.org",              "why": "Lightweight, open-source, easy to use"},
            {"name": "Kdenlive",        "url": "https://kdenlive.org",             "why": "Open-source, very feature-rich"},
            {"name": "OpenShot",        "url": "https://www.openshot.org",         "why": "Beginner friendly, free"},
        ],
        "game_engine": [
            {"name": "Godot",           "url": "https://godotengine.org",          "why": "100% free, MIT license, Python-like GDScript"},
            {"name": "Unity",           "url": "https://unity.com",                "why": "Industry standard, free personal plan"},
            {"name": "Unreal Engine",   "url": "https://www.unrealengine.com",     "why": "AAA quality, free to download"},
        ],
        "code_editor": [
            {"name": "VS Code",         "url": "https://code.visualstudio.com",    "why": "Best free editor, all languages"},
        ],
        "audio_editor": [
            {"name": "Audacity",        "url": "https://www.audacityteam.org",     "why": "Free, powerful audio editor"},
        ],
        "image_editor": [
            {"name": "GIMP",            "url": "https://www.gimp.org",             "why": "Free Photoshop alternative"},
            {"name": "Inkscape",        "url": "https://inkscape.org",             "why": "Free vector editor"},
        ],
    }

    def __init__(self):
        self._cache: Dict[str, Optional[str]] = {}
        self._scanned = False

    def find_app(self, name: str) -> Optional[str]:
        """Return exe path if found, else None."""
        key = name.lower().strip()
        if key in self._cache:
            return self._cache[key]

        paths = self.KNOWN_APPS.get(key, [])
        for p in paths:
            p = os.path.expandvars(p)
            if os.path.exists(p):
                self._cache[key] = p
                return p

        # Partial match
        for app_key, app_paths in self.KNOWN_APPS.items():
            if key in app_key or app_key in key:
                for p in app_paths:
                    p = os.path.expandvars(p)
                    if os.path.exists(p):
                        self._cache[key] = p
                        return p

        self._cache[key] = None
        return None

    def get_installed_apps(self) -> Dict[str, str]:
        """Return dict of {app_name: exe_path} for all found apps."""
        found = {}
        for name, paths in self.KNOWN_APPS.items():
            for p in paths:
                p = os.path.expandvars(p)
                if os.path.exists(p):
                    found[name] = p
                    break
        return found

    def is_installed(self, name: str) -> bool:
        return self.find_app(name) is not None

    def recommend(self, category: str) -> List[dict]:
        """Return recommended free apps for a category."""
        return self.RECOMMENDED.get(category, [])

    def detect_category(self, task: str) -> Optional[str]:
        """Detect what type of app is needed for a task."""
        t = task.lower()
        if any(w in t for w in ["video", "edit video", "cut video", "trim", "render video"]):
            return "video_editor"
        if any(w in t for w in ["game", "unity", "godot", "unreal", "game dev"]):
            return "game_engine"
        if any(w in t for w in ["code", "program", "python", "script"]):
            return "code_editor"
        if any(w in t for w in ["audio", "sound", "music edit", "podcast"]):
            return "audio_editor"
        if any(w in t for w in ["image", "photo", "design", "graphic"]):
            return "image_editor"
        return None


# ═══════════════════════════════════════════════════════════════════════════
# CHROME RESEARCHER — gets real-time info from the web
# ═══════════════════════════════════════════════════════════════════════════
class ChromeResearcher:
    """
    Fetches live web content for AI to learn from.
    Uses requests + simple HTML parsing (no selenium needed for most cases).
    Falls back to DuckDuckGo search snippets.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def search_and_summarize(self, query: str, max_chars: int = 1500) -> str:
        """Search the web and return a text summary for the AI to use."""
        # Check cache first
        cached = self.kb.recall_research(query)
        if cached:
            print(f"[RESEARCH] Cache hit for: {query[:50]}")
            return cached

        print(f"[RESEARCH] Searching: {query}")
        text = ""

        # Try DuckDuckGo first
        if DDG:
            try:
                with DDGS() as d:
                    results = list(d.text(query, max_results=6))
                snippets = []
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")[:300]
                    href = r.get("href", "")
                    snippets.append(f"[{title}] {body} ({href})")
                text = "\n".join(snippets)
                print(f"[RESEARCH] DDG got {len(text)} chars")
            except Exception as e:
                print(f"[RESEARCH] DDG error: {e}")

        # Try fetching top result page content
        if REQ and DDG and text:
            try:
                with DDGS() as d:
                    results = list(d.text(query, max_results=2))
                for r in results[:1]:
                    url = r.get("href", "")
                    if url and "youtube" not in url:
                        page_text = self._fetch_page(url, max_chars=800)
                        if page_text:
                            text = page_text + "\n\n" + text
                            break
            except Exception as e:
                print(f"[RESEARCH] Page fetch error: {e}")

        result = text[:max_chars] if text else ""
        if result:
            self.kb.cache_research(query, result)
        return result

    def research_app(self, app_name: str) -> str:
        """Research an app's UI, shortcuts, and how to use it."""
        query = f"{app_name} tutorial UI shortcuts how to use guide 2024"
        return self.search_and_summarize(query, max_chars=2000)

    def research_programming(self, language: str, topic: str) -> str:
        """Research programming language specifics."""
        query = f"{language} {topic} example tutorial 2024"
        return self.search_and_summarize(query, max_chars=2000)

    def _fetch_page(self, url: str, max_chars: int = 1000) -> str:
        """Fetch plain text from a webpage."""
        if not REQ:
            return ""
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=(5, 10))
            if r.status_code != 200:
                return ""
            html = r.text
            # Simple tag stripping
            text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.I)
            text = re.sub(r'<style[^>]*>.*?</style>',  ' ', text, flags=re.DOTALL | re.I)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
        except Exception:
            return ""


# ═══════════════════════════════════════════════════════════════════════════
# PENDRIVE MONITOR
# ═══════════════════════════════════════════════════════════════════════════
class PendriveMonitor:
    """Detects USB drives and can list/open files on them."""

    def get_drives(self) -> List[dict]:
        """Return list of removable drives."""
        drives = []
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    letter = chr(65 + i) + ":\\"
                    try:
                        drive_type = ctypes.windll.kernel32.GetDriveTypeW(letter)
                        # 2 = Removable, 3 = Fixed, 4 = Network, 5 = CD-ROM
                        label = ""
                        try:
                            import win32api
                            label = win32api.GetVolumeInformation(letter)[0]
                        except Exception:
                            pass
                        drives.append({
                            "letter": letter,
                            "type": drive_type,
                            "type_name": {2: "Removable/USB", 3: "Fixed", 4: "Network",
                                          5: "CD-ROM"}.get(drive_type, "Unknown"),
                            "label": label,
                            "is_usb": drive_type == 2
                        })
                    except Exception:
                        pass
        except Exception as e:
            print(f"[PENDRIVE] Drive detection error: {e}")
        return drives

    def get_usb_drives(self) -> List[dict]:
        return [d for d in self.get_drives() if d["is_usb"]]

    def list_files(self, drive_letter: str, extensions: List[str] = None) -> List[str]:
        """List files on a drive."""
        try:
            if not drive_letter.endswith("\\"):
                drive_letter += "\\"
            files = []
            for f in Path(drive_letter).iterdir():
                if f.is_file():
                    if extensions is None or f.suffix.lower() in extensions:
                        files.append(str(f))
            return sorted(files)[:100]
        except Exception as e:
            return [f"Error listing files: {e}"]

    def open_file(self, path: str) -> Tuple[bool, str]:
        try:
            os.startfile(path)
            return True, f"Opened: {Path(path).name}"
        except Exception as e:
            return False, f"Could not open {path}: {e}"


# ═══════════════════════════════════════════════════════════════════════════
# SCREEN CONTEXT MANAGER — continuous screen awareness
# ═══════════════════════════════════════════════════════════════════════════
class ScreenContextManager:
    """
    Continuously reads the screen OCR in the background.
    The brain uses this to know what's currently visible.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self._current_text = ""
        self._current_title = ""
        self._lock = threading.Lock()
        self._enabled = settings.get("V10_FEATURES", {}).get("continuous_screen_reading", True)
        self._reader = None
        if self._enabled:
            self._start_bg_reader()

    def _start_bg_reader(self):
        def _loop():
            # V12 FIX: Read every 15s not 3s — was flooding disk with screenshots
            # and slowing down OCR unnecessarily. Active window title is still
            # read every 2s (cheap) so AI knows which app is focused.
            last_ocr = 0.0
            OCR_INTERVAL = 15.0  # seconds between full OCR reads

            while True:
                try:
                    # Always track active window (very cheap)
                    title = self._get_active_window()
                    with self._lock:
                        self._current_title = title

                    # Full OCR only every 15 seconds
                    now = time.time()
                    if now - last_ocr >= OCR_INTERVAL:
                        if self._reader is None:
                            from vision.screen_vision import get_screen_reader
                            self._reader = get_screen_reader(self.settings)
                        text = self._reader.read(use_ai=False)
                        with self._lock:
                            self._current_text = text[:800]
                        last_ocr = now
                except Exception:
                    pass
                time.sleep(2.0)  # Poll window title every 2s

        t = threading.Thread(target=_loop, daemon=True, name="screen-reader")
        t.start()
        print("[SCREEN] Continuous reader started (OCR every 15s, window title every 2s)")

    def _get_active_window(self) -> str:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def get_context(self) -> Tuple[str, str]:
        """Returns (screen_text, window_title)."""
        with self._lock:
            return self._current_text, self._current_title

    def get_summary(self) -> str:
        text, title = self.get_context()
        parts = []
        if title:
            parts.append(f"Active window: {title}")
        if text:
            parts.append(f"Screen content: {text[:400]}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# TASK CHAIN PLANNER — breaks complex requests into steps
# ═══════════════════════════════════════════════════════════════════════════
class TaskChainPlanner:
    """
    Converts a multi-step request like 'open YouTube and play latest Arijit song'
    into an ordered list of atomic actions with timing delays.
    """

    # Pattern → list of action templates
    CHAINS = {
        # YouTube patterns
        r"(open|go to|launch)\s+youtube\s+and\s+(play|search|find)\s+(.+)": [
            {"action": "open_url",        "target": "https://youtube.com", "_delay": 2.5},
            {"action": "search_youtube",  "target": "{group3}",            "_delay": 1.5},
            {"action": "click_first_video","target": "",                   "_delay": 1.0},
        ],
        r"play\s+(.+)\s+(on|in)\s+youtube": [
            {"action": "open_url",        "target": "https://youtube.com", "_delay": 2.5},
            {"action": "search_youtube",  "target": "{group1}",            "_delay": 1.5},
            {"action": "click_first_video","target": "",                   "_delay": 1.0},
        ],
        r"play\s+latest\s+(.+)\s+song": [
            {"action": "open_url",        "target": "https://youtube.com", "_delay": 2.5},
            {"action": "search_youtube",  "target": "latest {group1} song 2024", "_delay": 1.5},
            {"action": "click_first_video","target": "",                   "_delay": 1.0},
        ],
        # Search on YouTube
        r"search\s+(.+)\s+on\s+youtube": [
            {"action": "open_url",        "target": "https://youtube.com", "_delay": 2.5},
            {"action": "search_youtube",  "target": "{group1}",            "_delay": 1.0},
        ],
        # Google search
        r"(google|search)\s+(.+)": [
            {"action": "search_web",      "target": "{group2}",            "_delay": 0},
        ],
        # Open app + do something
        r"open\s+(\w+)\s+and\s+(type|write|search)\s+(.+)": [
            {"action": "open_app",        "target": "{group1}",            "_delay": 2.0},
            {"action": "type_text",       "target": "{group3}",            "_delay": 1.5},
        ],
    }

    def plan(self, text: str) -> Optional[List[dict]]:
        """Returns an action chain if the text matches a known multi-step pattern."""
        t = text.lower().strip()
        for pattern, template in self.CHAINS.items():
            m = re.search(pattern, t, re.I)
            if m:
                chain = []
                for step in template:
                    action = dict(step)
                    # Substitute captured groups
                    for k, v in action.items():
                        if isinstance(v, str):
                            for i, g in enumerate(m.groups(), 1):
                                v = v.replace(f"{{group{i}}}", g or "")
                            action[k] = v
                    chain.append(action)
                print(f"[CHAIN] Matched pattern → {len(chain)} steps")
                return chain
        return None


# ═══════════════════════════════════════════════════════════════════════════
# INSTANT COMMAND ROUTER (zero latency)
# ═══════════════════════════════════════════════════════════════════════════
_SETTINGS: dict = {}

_INSTANT = {
    r'\b(time|waqt|samay|kitne baje|what time)\b':
        lambda: f"Sir, abhi {datetime.now():%I:%M %p} baj rahe hain.",
    r'\b(aaj|today|aaj ki date|what.*date|date kya)\b':
        lambda: f"Aaj {datetime.now():%A, %d %B %Y} hai, Sir.",
    r'\b(hello|hi|hey|namaste|hola|salaam)\b':
        lambda: _greet(),
    r'\b(kaisa|how are you|theek ho|sab theek)\b':
        lambda: "Main bilkul theek hoon, Sir! Aap batao, kya kaam hai?",
    r'\b(shukriya|thanks|thank you|dhanyawad)\b':
        lambda: "Koi baat nahi, Sir. Aur kuch kaam ho toh batao.",
    r'\b(jarvis version|version)\b':
        lambda: "Main JARVIS Omega V12 hoon, Sir. Advanced AI with real-time screen vision and app control.",
}


def _greet() -> str:
    h = datetime.now().hour
    t = "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")
    return f"{t}, Sir! JARVIS V12 hazir hai. Kya kaam hai?"


def instant_route(text: str) -> Optional[str]:
    for pat, fn in _INSTANT.items():
        if re.search(pat, text, re.I):
            return fn()
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT (V12 — comprehensive app control AI)
# ═══════════════════════════════════════════════════════════════════════════
SYS_V12 = """You are JARVIS V12, an advanced AI assistant on Windows 11.
User: {name}. Time: {time}.
Currently active window: {active_window}

YOUR CORE PHILOSOPHY:
"If a human can see it on screen and click it, I can too."
You control ANY app by reading the screen with OCR and clicking UI elements.
You are NOT limited to specific apps or hardcoded shortcuts.
You can control ANY software — video editors, game engines, IDEs, browsers,
design tools, DAWs, 3D tools, office apps, or any custom software.

CAPABILITIES:
1. UNIVERSAL APP CONTROL — Open, use, navigate ANY installed app.
   Use do_in_app to perform any action in the currently active app.
   You see the screen; find buttons/menus by their visible text and click.

2. ANY MICROCONTROLLER — Upload code to Arduino (Uno/Mega/Nano/Leonardo/Due/MKR),
   ESP32 (all variants: S2/S3/C3/C6), ESP8266/NodeMCU, Raspberry Pi Pico,
   STM32, Teensy, or ANY USB serial device. Not just Uno and ESP32.

3. HOME AUTOMATION via USB — Control home appliances (lights, fans, AC, TV)
   through a USB-connected Arduino/ESP32 relay board. NO Alexa, NO WiFi,
   NO cloud. Pure USB serial. Send any command the relay understands.

4. SCREEN VISION — Continuously reads the screen. You always know what
   is visible, which buttons exist, which app is open.

5. WEB RESEARCH — Search the web for real-time info, app tutorials,
   programming guides, latest news. Save learned info to memory.

6. USB/PENDRIVE — Detect, list files, and open files from any USB drive.

7. CODE EXECUTION — Run Python scripts and terminal commands directly.

8. UNIVERSAL LEARNING — After every task, save what you learned about
   the app's UI, so next time you do it faster.

LANGUAGE RULE:
- Reply in Hinglish (Hindi in English script). Example:
  "Sir, main DaVinci Resolve mein Export button click kar raha hoon."
- NEVER Devanagari script. Keep replies 1-4 sentences. Always say "Sir".

SCREEN CONTEXT (what's visible right now):
{screen_context}

APP CONTEXT (recent history):
{app_context}

TASK RULES:
- Multi-step tasks: embed ALL actions in the SAME reply, in order.
- App NOT installed: say so, recommend best FREE alternative with download link.
- NEVER assume an app is installed (e.g. Spotify) — check app_context first.
- For ANY app action: use do_in_app with a plain English description.
  JARVIS will find the right button/menu by reading the screen.
- For home automation: use home_control. It sends to USB serial relay board.
- Logical context: if Sir said "open YouTube" earlier, "play something" means YouTube.

EMBED EXACTLY this JSON per action (multiple actions allowed):
{{"action":"ACTION","target":"VALUE","delay":SECONDS}}

═══ ALL AVAILABLE ACTIONS ═══

APP LAUNCH / WINDOW:
  open_app         target=app_name (ANY app — finds it automatically)
  close_app        target=app_name_or_window_title
  minimize_app     target=window_title
  maximize_app     target=window_title
  focus_window     target=window_title
  list_windows     (shows all open windows)
  scan_all_apps    (scan all installed apps)

UNIVERSAL UI CONTROL (works on ANY open app):
  do_in_app        target="click Export button"  (natural language action)
  click_ui         target="text of button to click"
  click_menu       target="File > Export > Export as MP4"
  find_and_click   target="button or text to find and click"
  find_and_type    target="field_name|text to type"
  app_action       target="save / export / render / build / run / etc."
  app_shortcut     target="description of shortcut needed"
  read_ui          (lists all visible UI elements)

WEB / BROWSER:
  open_url         target=url
  search_web       target=search query
  search_youtube   target=search query
  click_first_video  (click first YouTube result after search)
  play_music       target=song/artist name
  browser_back     browser_refresh  browser_new_tab  browser_close_tab
  fill_form        target="field_name|value"

KEYBOARD / MOUSE:
  type_text        target=text to type
  hotkey           target=ctrl+s / alt+f4 / etc.
  press_key        target=key name
  mouse_click      target=x,y
  double_click     target=x,y
  right_click      target=x,y
  mouse_move       target=x,y
  mouse_scroll_up  mouse_scroll_down
  drag_to          target=x1,y1 x2,y2
  clear_field

SCREEN:
  screenshot
  read_screen      (OCR full screen)
  find_text_on_screen  target=text to find

SYSTEM:
  volume_up  volume_down  mute  lock_screen
  system_info  list_processes  kill_process target=process_name
  run_python   target=python code
  run_command  target=shell command
  wait         target=seconds

FILES:
  open_file  save_file  save_as  new_file  target=path or filename

USB STORAGE:
  list_usb_drives    list_usb_files  target=drive_letter
  open_usb_file      target=filename

USB SERIAL DEVICES (microcontrollers, 3D printers, CNC, custom hardware):
  list_serial_devices  (see all connected USB serial devices)
  serial_send      target="PORT|command|baud"  (send any command to any device)

FIRMWARE UPLOAD (ANY microcontroller — not just Arduino):
  upload_firmware  target="sketch_path|board_name|port"
  board_name examples: "arduino uno", "arduino mega", "arduino nano",
    "esp32", "esp32-s3", "esp32-c3", "esp8266", "nodemcu", "pico",
    "stm32", "teensy 4.1", "arduino due", "wemos d1 mini", "esp32 cam"

HOME AUTOMATION via USB SERIAL (NO Alexa, NO WiFi, pure USB relay):
  home_control     target="light on" / "fan off" / "ac on" / "all off"
  home_custom      target="PORT|CUSTOM_COMMAND|baud"
  home_status      (check what relay board is connected)

KNOWLEDGE:
  research_app     target=app_name (research UI/shortcuts via web)
  learn_and_save   target=knowledge to save
  recall           target=task or topic to recall
"""


def _sys_prompt(name: str, screen_ctx: str = "", active_window: str = "",
                app_context: str = "") -> str:
    return SYS_V12.format(
        name=name,
        time=datetime.now().strftime("%I:%M %p, %A"),
        active_window=active_window or "Desktop",
        screen_context=screen_ctx[:400] if screen_ctx else "No screen data",
        app_context=app_context[:300] if app_context else "No app context"
    )


# ═══════════════════════════════════════════════════════════════════════════
# ACTION EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════
def extract_actions(response: str) -> List[dict]:
    actions = []
    for match in re.finditer(r'\{[^{}]*?"action"\s*:\s*"[^"]+?"[^{}]*?\}', response, re.DOTALL):
        try:
            obj = json.loads(match.group())
            if "action" in obj and obj["action"]:
                actions.append(obj)
        except json.JSONDecodeError:
            pass

    if not actions:
        for match in re.finditer(r'"action"\s*:\s*"([^"]+)"', response):
            action_name = match.group(1)
            seg = response[match.start():match.start() + 200]
            tm  = re.search(r'"target"\s*:\s*"([^"]*)"', seg)
            target = tm.group(1) if tm else ""
            actions.append({"action": action_name, "target": target})

    if actions:
        print(f"[BRAIN] Extracted {len(actions)} action(s): {[a['action'] for a in actions]}")
    return actions


def strip_actions(response: str) -> str:
    cleaned = re.sub(r'\s*\{[^{}]*?"action"[^{}]*?\}\s*', ' ', response, flags=re.DOTALL)
    return re.sub(r'\s+', ' ', cleaned).strip()


# ═══════════════════════════════════════════════════════════════════════════
# OLLAMA INTERFACE
# ═══════════════════════════════════════════════════════════════════════════
def check_ollama_running(url: str) -> Tuple[bool, List[str]]:
    if not REQ:
        return False, []
    try:
        r = requests.get(f"{url}/api/tags", timeout=(4, 8))
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return True, models
    except Exception:
        pass
    return False, []


def _call_ollama(url: str, model: str, msgs: list,
                 max_tokens: int = 200, timeout: float = 30.0) -> Optional[str]:
    """
    V12 FIX: 
    - Default max_tokens 200 (was 500) — faster response
    - Default timeout 30s (was 90s) — fail fast, try next model
    - Uses streaming=True for faster first-token delivery
    - Collects full stream before returning
    """
    if not REQ:
        return None
    try:
        body = {
            "model": model,
            "messages": msgs,
            "stream": True,   # streaming = faster first token
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.65,
                "top_p":       0.85,
                "num_ctx":     2048,   # smaller context = faster
                "repeat_penalty": 1.1,
            }
        }
        r = requests.post(f"{url}/api/chat", json=body,
                          timeout=(5, timeout), stream=True)
        if r.status_code != 200:
            print(f"[OLLAMA] HTTP {r.status_code}")
            return None

        # Collect streamed tokens
        collected = []
        for line in r.iter_lines(chunk_size=64):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    collected.append(token)
                if chunk.get("done", False):
                    break
            except json.JSONDecodeError:
                continue

        result = "".join(collected).strip()
        if result:
            print(f"[OLLAMA] ✓ {model}: {len(result)} chars")
            return result
        return None

    except requests.exceptions.ConnectionError:
        print(f"[OLLAMA] Connection refused at {url}")
    except requests.exceptions.Timeout:
        print(f"[OLLAMA] Timeout on '{model}' (>{timeout}s)")
    except Exception as e:
        print(f"[OLLAMA] Error on '{model}': {e}")
    return None


def call_first_available(url: str, model_list: List[Tuple[str, int]],
                         msgs: list, timeout: float = 30.0) -> Optional[str]:
    """
    V12 FIX: Run models SEQUENTIALLY but with tight 25s timeout each.
    Total cap = 30s. First model that responds wins.
    Sequential avoids GPU contention (one model at a time is faster on single GPU).
    """
    per_model = min(25.0, timeout / max(len(model_list), 1))
    for model, tok in model_list:
        t0 = time.time()
        result = _call_ollama(url, model, msgs, tok, per_model)
        elapsed = time.time() - t0
        if result:
            print(f"[BRAIN] ✓ '{model}' responded in {elapsed:.1f}s")
            return result
        print(f"[BRAIN] '{model}' failed after {elapsed:.1f}s, trying next")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# NEEDS SEARCH GUARD
# ═══════════════════════════════════════════════════════════════════════════
_SKIP_SEARCH = [
    r'\b(time|waqt|samay|kitne baje)\b',
    r'\b(today|aaj|date)\b',
    r'\b(hello|hi|hey|namaste|thanks|shukriya)\b',
    r'\b(version|jarvis version)\b',
    r'\b(open|close|minimize|maximize|click)\b',
    r'\b(type|write|press|hotkey)\b',
    r'\b(volume|mute|screenshot|lock)\b',
]

_NEEDS_SEARCH = [
    r'\b(search|find|google|news|latest|2024|2025|2026|who is|what is|explain|research)\b',
    r'\b(how to|tutorial|guide|learn|study)\b',
    r'\b(price|cost|buy|download|install)\b',
    r'\b(weather|stock|score|result)\b',
    r'\b(app info|shortcut|feature of|how does)\b',
]


def needs_search(text: str) -> bool:
    tl = text.lower()
    for p in _SKIP_SEARCH:
        if re.search(p, tl):
            return False
    for p in _NEEDS_SEARCH:
        if re.search(p, tl):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# HINDI → HINGLISH
# ═══════════════════════════════════════════════════════════════════════════
_HM = {
    'नमस्ते':'namaste','धन्यवाद':'dhanyavaad','शुक्रिया':'shukriya',
    'हाँ':'haan','नहीं':'nahin','ठीक':'theek','बहुत':'bahut',
    'अच्छा':'achha','करो':'karo','करें':'karein','बताओ':'batao',
    'देखो':'dekho','खोलो':'kholo','बंद':'band','चालू':'chaalu',
    'क्या':'kya','कैसे':'kaise','कहाँ':'kahaan','कब':'kab',
    'क्यों':'kyun','कौन':'kaun','कितना':'kitna','मैं':'main',
    'आप':'aap','हम':'hum','वह':'woh','यह':'yeh','अभी':'abhi',
    'आज':'aaj','कल':'kal','सुबह':'subah','शाम':'shaam','रात':'raat',
    'हूँ':'hoon','है':'hai','हैं':'hain','था':'tha','होगा':'hoga',
    'गया':'gaya','रहा':'raha','और':'aur','या':'ya','लेकिन':'lekin',
    'के':'ke','की':'ki','का':'ka','में':'mein','पर':'par',
    'से':'se','को':'ko','ने':'ne','तो':'to','भी':'bhi',
    'सही':'sahi','काम':'kaam','नाम':'naam','बात':'baat',
    'मदद':'madad','जरूरत':'zaroorat','शुरू':'shuru','खत्म':'khatam',
    'सर':'Sir','दिखाओ':'dikhao','चलाओ':'chalaao','खोज':'search',
}


def hindi_to_hinglish(text: str) -> str:
    for h, r in _HM.items():
        text = text.replace(h, r)
    text = re.sub(r'[\u0900-\u097F]+', lambda m: f'[{m.group()}]', text)
    return text


# ═══════════════════════════════════════════════════════════════════════════
# MAIN BRAIN
# ═══════════════════════════════════════════════════════════════════════════
class JarvisBrain:
    def __init__(self, settings: dict):
        global _SETTINGS
        self.settings = settings
        _SETTINGS = settings

        # Sub-systems
        self.kb         = KnowledgeBase()
        self.researcher = ChromeResearcher(self.kb)
        self.scanner    = AppScanner()
        self.pendrive   = PendriveMonitor()
        self.planner    = TaskChainPlanner()
        self.screen_ctx = ScreenContextManager(settings)

        # Runtime references
        self.automation          = None
        self.vision_enabled      = settings.get("V10_FEATURES", {}).get("vision_enabled", True)
        self.web_search_enabled  = settings.get("V10_FEATURES", {}).get("web_search_enabled", True)
        self.chrome_research     = settings.get("V10_FEATURES", {}).get("chrome_research_enabled", True)

        # Ollama config
        self.url    = settings.get("ollama_url", "http://localhost:11434")
        self.models = settings.get("V10_MODELS", {})

        # V12 FIX: Model lists updated for user's actual Ollama library
        # Available: llama3.2, qwen3.5:4b, phi3:3.8b, deepseek-coder:1.3b, qwen3-vl:2b
        # Strategy: FAST model first (phi3 = fastest), full model second
        # max_tokens reduced to 200 — shorter = faster response
        _chat   = self.models.get("chat",      "llama3.2")
        _fast   = self.models.get("fast",      "phi3:3.8b")
        _code   = self.models.get("code",      "deepseek-coder:1.3b")
        _reason = self.models.get("reasoning", "qwen3.5:4b")
        _vision = self.models.get("vision",    "qwen3-vl:2b")

        # FAST model first → full model fallback
        self._chat_models     = [(_fast, 200), (_chat, 200)]
        self._search_models   = [(_fast, 220), (_reason, 250), (_chat, 200)]
        self._code_models     = [(_code, 400), (_fast, 300), (_chat, 250)]
        self._creative_models = [(_chat, 250), (_fast, 200)]
        self._vision_models   = [(_vision, 200), (_fast, 200)]

        ok, installed = check_ollama_running(self.url)
        if ok:
            print(f"[BRAIN] ✓ Ollama running | Models: {installed}")
        else:
            print("[BRAIN] ⚠ Ollama not running — run: ollama serve")

        # Pre-scan installed apps
        found = self.scanner.get_installed_apps()
        print(f"[BRAIN] ✓ Found {len(found)} installed apps: {list(found.keys())[:8]}...")

        print("[BRAIN] ✓ V12 Brain ready with full app control + screen vision")

    # ── Build message list ─────────────────────────────────────────────────
    def _build_msgs(self, user_input: str,
                    screen_ctx: str = "", active_window: str = "",
                    app_ctx: str = "") -> list:
        # V12 FIX: trim screen context aggressively — it was causing timeouts
        # Keep only first 120 chars of screen text (models load faster)
        trimmed_screen = (screen_ctx[:120] + "...") if len(screen_ctx) > 120 else screen_ctx
        sys = _sys_prompt(
            self.settings.get("user_name", "Sir"),
            trimmed_screen, active_window, app_ctx
        )
        msgs = [{"role": "system", "content": sys}]
        for h in self.kb.recent_conv(8):
            msgs.append({"role": "user",      "content": h["user"]})
            msgs.append({"role": "assistant", "content": h["assistant"]})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    # ── App check helper ───────────────────────────────────────────────────
    def _check_app_available(self, app_name: str) -> Tuple[bool, str]:
        """Returns (is_installed, message_for_user)."""
        if self.scanner.is_installed(app_name):
            return True, ""
        # Check category and recommend
        category = self.scanner.detect_category(app_name)
        recs = self.scanner.recommend(category) if category else []
        if recs:
            rec_text = " | ".join(
                f"{r['name']} ({r['why']}) → {r['url']}" for r in recs[:3]
            )
            return False, (
                f"Sir, '{app_name}' install nahi hai laptop pe. "
                f"Yeh free alternatives hain: {rec_text}"
            )
        return False, (
            f"Sir, '{app_name}' laptop pe nahi mila. "
            f"Pehle install karein."
        )

    # ── Main process ───────────────────────────────────────────────────────
    def process(self, text: str, task_hint: str = "chat") -> Tuple[str, List[dict]]:
        t0 = time.time()
        tl = text.lower().strip()

        # ── 0. Instant responses ──────────────────────────────────────────
        quick = instant_route(text)
        if quick:
            self.kb.save_conv(text, quick)
            return quick, []

        # ── 1. App availability check for direct app commands ─────────────
        app_open_match = re.search(
            r'\b(open|launch|start|run)\s+([\w\s]+?)(?:\s+and|\s+to|\s+for|$)', tl
        )
        if app_open_match:
            app_name = app_open_match.group(2).strip()
            # Skip generic words
            generic = {"the", "a", "an", "my", "this", "that", "it", "browser",
                       "terminal", "file", "folder", "screen"}
            if app_name not in generic and len(app_name) > 2:
                installed, msg = self._check_app_available(app_name)
                if not installed and msg:
                    self.kb.save_conv(text, msg)
                    return msg, []

        # ── 2. Task chain planning ─────────────────────────────────────────
        chain = self.planner.plan(text)
        if chain:
            resp = f"Sir, main yeh multi-step task execute kar raha hoon: {len(chain)} steps"
            self.kb.save_conv(text, resp)
            self.kb.set_ctx("last_task", text)
            return resp, chain

        # ── 3. Screen context (continuous reader) ─────────────────────────
        # V12 FIX: Only include screen text if query is screen-related
        # Injecting large screen OCR into every prompt was causing timeouts
        _raw_screen, active_window = self.screen_ctx.get_context()
        screen_text = _raw_screen if task_hint == "screen" else ""

        # ── 4. App context from KB ────────────────────────────────────────
        app_ctx = ""
        last_app = self.kb.get_ctx("last_app_opened") or ""
        if last_app:
            app_info = self.kb.get_app_info(last_app)
            if app_info and app_info.get("ui_notes"):
                app_ctx = f"Last app: {last_app} | UI: {app_info['ui_notes'][:200]}"

        # ── 5. Research augmentation ───────────────────────────────────────
        user_input = text
        extra_context = []

        # Web/Chrome research for info queries
        if self.web_search_enabled and needs_search(text):
            print("[BRAIN] Running web research…")
            if self.chrome_research:
                sr = self.researcher.search_and_summarize(text, max_chars=1200)
            else:
                sr = self._ddg_search(text)
            if sr:
                extra_context.append(f"[Web Research]\n{sr}")

        # App UI research if user wants to use an app we don't know
        if any(w in tl for w in ["how to use", "tutorial", "feature", "shortcut"]):
            for app_name in self.scanner.KNOWN_APPS:
                if app_name in tl:
                    cached = self.kb.get_app_info(app_name)
                    if not (cached and cached.get("ui_notes")):
                        print(f"[BRAIN] Researching {app_name} UI…")
                        ui_info = self.researcher.research_app(app_name)
                        if ui_info:
                            self.kb.save_app_info(
                                app_name,
                                self.scanner.find_app(app_name) or "",
                                ui_notes=ui_info[:800]
                            )
                            extra_context.append(f"[App Info: {app_name}]\n{ui_info[:500]}")
                    elif cached.get("ui_notes"):
                        extra_context.append(f"[App Info: {app_name}]\n{cached['ui_notes'][:400]}")
                    break

        # Programming language research
        if any(w in tl for w in ["code", "program", "write in", "syntax", "how to"]):
            lang_match = re.search(
                r'\b(python|javascript|c\+\+|java|rust|kotlin|arduino|esp32|lua|gdscript)\b',
                tl, re.I
            )
            if lang_match:
                lang = lang_match.group(1)
                topic = re.sub(
                    r'\b(code|program|write|how to|in|using|with|for)\b', '', tl
                ).strip()
                cached_r = self.kb.recall_research(f"{lang} {topic}")
                if not cached_r:
                    research = self.researcher.research_programming(lang, topic)
                    if research:
                        extra_context.append(f"[{lang} Research]\n{research[:500]}")

        # Pendrive queries
        if any(w in tl for w in ["pendrive", "usb", "flash drive", "usb drive", "pendrive"]):
            drives = self.pendrive.get_usb_drives()
            if drives:
                drive_info = ", ".join(
                    f"{d['letter']} ({d['label'] or 'Unlabeled'})" for d in drives
                )
                extra_context.append(f"[USB Drives Connected]: {drive_info}")
            else:
                extra_context.append("[USB Drives]: No USB drives detected")

        if extra_context:
            user_input = text + "\n\n" + "\n\n".join(extra_context)

        # ── 6. Screen context injection ────────────────────────────────────
        if screen_text:
            # Inject screen context into system prompt (not user msg)
            pass  # Already in sys prompt via screen_ctx parameter

        # ── 7. Auto-detect task type ───────────────────────────────────────
        if task_hint == "chat":
            if any(w in tl for w in ["code", "python", "script", "function",
                                      "program", "bug", "arduino", "esp32"]):
                task_hint = "code"
            elif any(w in tl for w in ["write", "essay", "story", "poem",
                                        "creative", "design"]):
                task_hint = "creative"
            elif any(w in tl for w in ["search", "find", "news", "latest",
                                        "who is", "what is", "explain",
                                        "research", "how to"]):
                task_hint = "search"
            elif any(w in tl for w in ["screen", "dekho", "read screen",
                                        "what is on", "dikhao"]):
                task_hint = "screen"

        # ── 8. Pick model list ─────────────────────────────────────────────
        model_list = {
            "screen":   self._vision_models,
            "search":   self._search_models,
            "code":     self._code_models,
            "creative": self._creative_models,
        }.get(task_hint, self._chat_models)

        msgs = self._build_msgs(user_input, screen_text, active_window, app_ctx)

        # ── 9. Call Ollama ─────────────────────────────────────────────────
        print(f"[BRAIN] Task={task_hint} | Models: {[m[0] for m in model_list]}")
        raw = call_first_available(self.url, model_list, msgs, timeout=30.0)

        if not raw:
            ok, _ = check_ollama_running(self.url)
            if not ok:
                raw = ("Sir, Ollama chal nahi raha. "
                       "Terminal mein likhen: ollama serve")
            else:
                raw = ("Sir, model response nahi diya. "
                       "Thoda wait karein — model load ho raha hoga.")

        # ── 10. Extract actions + update context ───────────────────────────
        actions = []
        try:
            actions = extract_actions(raw)
        except Exception as e:
            print(f"[BRAIN] Action extract error: {e}")

        # Update context from actions
        for act in actions:
            a = act.get("action", "")
            t_val = act.get("target", "")
            if a == "open_app":
                self.kb.set_ctx("last_app_opened", t_val)
                self.kb.save_app_info(t_val, self.scanner.find_app(t_val) or "",
                                      installed=self.scanner.is_installed(t_val))
            elif a in ("open_url", "search_web"):
                self.kb.set_ctx("last_url", t_val)

        # Save task result to knowledge base
        self.kb.save_task(text, raw[:500], last_app,
                          steps=[a.get("action") for a in actions])

        try:
            clean = strip_actions(raw)
        except Exception:
            clean = raw

        clean = hindi_to_hinglish(clean)
        self.kb.save_conv(text, clean)
        print(f"[BRAIN] ✓ Done in {time.time()-t0:.2f}s | {len(actions)} action(s)")
        return clean, actions

    def _ddg_search(self, query: str, n: int = 5) -> str:
        if not DDG:
            return ""
        try:
            with DDGS() as d:
                results = list(d.text(query, max_results=n))
            return "\n".join(
                f"• {r.get('title','')}: {r.get('body','')[:120]}"
                for r in results
            )
        except Exception as e:
            print(f"[DDG] Error: {e}")
            return ""

    def clear_history(self):
        pass  # History is in SQLite, no in-memory clear needed

    def get_installed_apps_summary(self) -> str:
        found = self.scanner.get_installed_apps()
        if not found:
            return "No apps found"
        return ", ".join(f"{k}" for k in list(found.keys())[:20])
