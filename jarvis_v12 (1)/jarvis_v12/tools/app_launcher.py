"""
tools/app_launcher.py — JARVIS V12

UNIVERSAL APP LAUNCHER + FINDER
Finds and opens ANY app on Windows — installed, portable, Store apps.
Goes far beyond a hardcoded list by scanning the filesystem.
"""
from __future__ import annotations

import os, re, glob, subprocess, webbrowser, time
from pathlib import Path
from typing import Optional, Tuple, List, Dict

# ── pygetwindow ───────────────────────────────────────────────────────────
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
    import ctypes
    CTYPES = True
except Exception:
    CTYPES = False


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH ROOTS — every place Windows apps can live
# ══════════════════════════════════════════════════════════════════════════════
SEARCH_ROOTS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    os.path.expandvars(r"%APPDATA%"),
    os.path.expandvars(r"%LOCALAPPDATA%"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps"),
    os.path.expandvars(r"%USERPROFILE%\Desktop"),
    os.path.expandvars(r"%PUBLIC%\Desktop"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Roaming"),
    r"C:\tools",
    r"C:\dev",
    r"D:\Program Files",
    r"D:\Software",
]

# Web fallbacks for apps that are primarily web-based
WEB_FALLBACKS: Dict[str, str] = {
    "youtube":    "https://youtube.com",
    "gmail":      "https://gmail.com",
    "google":     "https://google.com",
    "google drive":"https://drive.google.com",
    "google meet":"https://meet.google.com",
    "google docs":"https://docs.google.com",
    "github":     "https://github.com",
    "linkedin":   "https://linkedin.com",
    "twitter":    "https://x.com",
    "reddit":     "https://reddit.com",
    "wikipedia":  "https://wikipedia.org",
    "netflix":    "https://netflix.com",
    "hotstar":    "https://hotstar.com",
    "amazon":     "https://amazon.in",
    "amazon prime":"https://primevideo.com",
    "flipkart":   "https://flipkart.com",
    "chatgpt":    "https://chat.openai.com",
    "gemini":     "https://gemini.google.com",
    "claude":     "https://claude.ai",
    "perplexity": "https://perplexity.ai",
    "notion":     "https://notion.so",
    "figma":      "https://figma.com",
    "canva":      "https://canva.com",
    "trello":     "https://trello.com",
    "jira":       "https://atlassian.net",
    "slack":      "https://slack.com",
    "vercel":     "https://vercel.com",
    "heroku":     "https://heroku.com",
    "stackoverflow":"https://stackoverflow.com",
    "pypi":       "https://pypi.org",
    "npm":        "https://npmjs.com",
    "huggingface":"https://huggingface.co",
    "colab":      "https://colab.research.google.com",
    "kaggle":     "https://kaggle.com",
    "leetcode":   "https://leetcode.com",
    "hackerrank": "https://hackerrank.com",
    "olx":        "https://olx.in",
    "irctc":      "https://irctc.co.in",
    "paytm":      "https://paytm.com",
    "phonepe":    "https://phonepe.com",
}

# System commands that don't need a path
SYSTEM_COMMANDS: Dict[str, str] = {
    "notepad":          "notepad.exe",
    "calculator":       "calc.exe",
    "paint":            "mspaint.exe",
    "wordpad":          "wordpad.exe",
    "cmd":              "cmd.exe",
    "command prompt":   "cmd.exe",
    "powershell":       "powershell.exe",
    "powershell ise":   "powershell_ise.exe",
    "windows terminal": "wt.exe",
    "terminal":         "wt.exe",
    "explorer":         "explorer.exe",
    "file explorer":    "explorer.exe",
    "task manager":     "taskmgr.exe",
    "registry editor":  "regedit.exe",
    "services":         "services.msc",
    "device manager":   "devmgmt.msc",
    "disk management":  "diskmgmt.msc",
    "event viewer":     "eventvwr.msc",
    "group policy":     "gpedit.msc",
    "resource monitor": "perfmon.exe",
    "snipping tool":    "snippingtool.exe",
    "sticky notes":     "stikynot.exe",
    "magnifier":        "magnify.exe",
    "narrator":         "narrator.exe",
    "on screen keyboard":"osk.exe",
    "remote desktop":   "mstsc.exe",
    "hyper-v":          "virtmgmt.msc",
    "character map":    "charmap.exe",
    "disk cleanup":     "cleanmgr.exe",
    "defragment":       "dfrgui.exe",
    "system config":    "msconfig.exe",
    "dxdiag":           "dxdiag.exe",
    "winver":           "winver.exe",
    "settings":         "ms-settings:",
    "windows settings": "ms-settings:",
    "bluetooth settings":"ms-settings:bluetooth",
    "wifi settings":    "ms-settings:network-wifi",
    "display settings": "ms-settings:display",
    "sound settings":   "ms-settings:sound",
    "privacy settings": "ms-settings:privacy",
    "update settings":  "ms-settings:windowsupdate",
    "apps settings":    "ms-settings:appsfeatures",
    "control panel":    "control.exe",
    "network connections":"ncpa.cpl",
    "firewall":         "firewall.cpl",
    "add remove programs":"appwiz.cpl",
    "date time":        "timedate.cpl",
    "sound":            "mmsys.cpl",
    "screen saver":     "desk.cpl",
}

# Known paths for very common apps (checked first for speed)
KNOWN_PATHS: Dict[str, List[str]] = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ],
    "vscode":  [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")],
    "vlc":     [r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"],
    "spotify": [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")],
    "steam":   [r"C:\Program Files (x86)\Steam\steam.exe"],
    "discord": [os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-1.0.9005\Discord.exe")],
    "whatsapp":[os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe")],
    "telegram":[os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe")],
    "zoom":    [os.path.expandvars(r"%APPDATA%\Zoom\bin\Zoom.exe")],
    "teams":   [os.path.expandvars(r"%APPDATA%\Microsoft\Teams\current\Teams.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Teams\Update.exe")],
    "obs":     [r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"],
    "blender": [r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender\blender.exe"],
    "godot":   [r"C:\Program Files\Godot\Godot.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Godot\Godot.exe")],
    "winrar":  [r"C:\Program Files\WinRAR\WinRAR.exe"],
    "7zip":    [r"C:\Program Files\7-Zip\7zFM.exe"],
    "git":     [r"C:\Program Files\Git\bin\git-bash.exe"],
    "git bash":[r"C:\Program Files\Git\bin\git-bash.exe"],
    "python":  ["python"],
    "nodejs":  ["node"],
    "word":    [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\WINWORD.EXE"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft Office\root\Office16\WINWORD.EXE")],
    "excel":   [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\EXCEL.EXE")],
    "powerpoint":[os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\POWERPNT.EXE")],
    "outlook": [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\OUTLOOK.EXE")],
    "access":  [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\MSACCESS.EXE")],
    "onenote": [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Office\root\Office16\ONENOTE.EXE")],
    "davinci resolve": [r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"],
    "shotcut": [r"C:\Program Files\Shotcut\shotcut.exe"],
    "kdenlive":[r"C:\Program Files\kdenlive\bin\kdenlive.exe"],
    "openshot":[r"C:\Program Files\OpenShot Video Editor\openshot-qt.exe"],
    "handbrake":[r"C:\Program Files\HandBrake\HandBrake.exe"],
    "gimp":    [r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe",
                r"C:\Program Files\GIMP 3\bin\gimp-3.0.exe"],
    "inkscape":[r"C:\Program Files\Inkscape\inkscape.exe"],
    "krita":   [r"C:\Program Files\Krita\bin\krita.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krita\bin\krita.exe")],
    "photoshop":[os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe Photoshop 2024\Photoshop.exe")],
    "illustrator":[os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe Illustrator 2024\Support Files\Contents\Windows\Illustrator.exe")],
    "premiere":[os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe Premiere Pro 2024\Adobe Premiere Pro.exe")],
    "after effects":[os.path.expandvars(r"%PROGRAMFILES%\Adobe\Adobe After Effects 2024\Support Files\AfterFX.exe")],
    "audacity":[r"C:\Program Files\Audacity\Audacity.exe"],
    "reaper":  [r"C:\Program Files\REAPER (x64)\reaper.exe"],
    "lmms":    [r"C:\Program Files\LMMS\lmms.exe"],
    "fl studio":[r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
                 r"C:\Program Files (x86)\Image-Line\FL Studio 21\FL.exe"],
    "unity hub":[os.path.expandvars(r"%PROGRAMFILES%\Unity\Hub\Unity Hub.exe")],
    "unreal":  [os.path.expandvars(r"%PROGRAMFILES%\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe")],
    "android studio":[os.path.expandvars(r"%LOCALAPPDATA%\Programs\Android Studio\bin\studio64.exe")],
    "pycharm": [os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\PyCharm\bin\pycharm64.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\PyCharm Community Edition\bin\pycharm64.exe")],
    "intellij":[os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\IntelliJIdea\bin\idea64.exe")],
    "clion":   [os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\CLion\bin\clion64.exe")],
    "webstorm":[os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\WebStorm\bin\webstorm64.exe")],
    "eclipse": [r"C:\eclipse\eclipse.exe"],
    "arduino": [r"C:\Program Files\Arduino IDE\Arduino IDE.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\arduino-ide\Arduino IDE.exe"),
                r"C:\Program Files (x86)\Arduino\arduino.exe"],
    "notepad++":[r"C:\Program Files\Notepad++\notepad++.exe",
                 r"C:\Program Files (x86)\Notepad++\notepad++.exe"],
    "sublime":  [r"C:\Program Files\Sublime Text\sublime_text.exe",
                 r"C:\Program Files\Sublime Text 4\sublime_text.exe"],
    "atom":     [os.path.expandvars(r"%LOCALAPPDATA%\atom\atom.exe")],
    "vim":      [r"C:\Program Files\Vim\vim91\gvim.exe"],
    "gedit":    [r"C:\Program Files\gedit\bin\gedit.exe"],
    "msbuild":  [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe")],
    "visual studio": [os.path.expandvars(r"%PROGRAMFILES%\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe")],
}


# ── Runtime path cache ────────────────────────────────────────────────────
_PATH_CACHE: Dict[str, Optional[str]] = {}


def find_app_path(name: str) -> Optional[str]:
    """
    Find any app on Windows.
    1. Check system commands (notepad, calc, etc.)
    2. Check known paths
    3. Search filesystem
    4. Search Windows Registry
    5. Check PATH
    Returns exe path or None.
    """
    key = name.lower().strip()

    # Cache hit
    if key in _PATH_CACHE:
        return _PATH_CACHE[key]

    # 1. System built-ins
    if key in SYSTEM_COMMANDS:
        _PATH_CACHE[key] = SYSTEM_COMMANDS[key]
        return SYSTEM_COMMANDS[key]

    # 2. Known paths
    for app_key, paths in KNOWN_PATHS.items():
        if key == app_key or key in app_key or app_key in key:
            for p in paths:
                p = os.path.expandvars(str(p))
                if os.path.exists(p):
                    _PATH_CACHE[key] = p
                    return p

    # 3. Filesystem search
    exe_name  = key.replace(" ", "") + ".exe"
    exe_name2 = key.replace(" ", "_") + ".exe"
    exe_name3 = key.replace(" ", "-") + ".exe"
    
    for root in SEARCH_ROOTS:
        root = os.path.expandvars(root)
        if not os.path.isdir(root):
            continue
        try:
            for candidate in [exe_name, exe_name2, exe_name3]:
                pattern = os.path.join(root, "**", candidate)
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    best = sorted(matches, key=len)[0]  # Shortest = most direct
                    _PATH_CACHE[key] = best
                    return best
        except (PermissionError, OSError):
            continue

    # 4. Windows Registry (installed apps)
    reg_path = _find_via_registry(name)
    if reg_path:
        _PATH_CACHE[key] = reg_path
        return reg_path

    # 5. PATH check
    import shutil
    found = shutil.which(key) or shutil.which(exe_name)
    if found:
        _PATH_CACHE[key] = found
        return found

    # 6. Windows Store apps (via ms-windows-store: scheme)
    # These open with winget or directly
    store_check = _find_store_app(name)
    if store_check:
        _PATH_CACHE[key] = store_check
        return store_check

    _PATH_CACHE[key] = None
    return None


def _find_via_registry(name: str) -> Optional[str]:
    """Search Windows registry for installed app paths."""
    try:
        import winreg
        reg_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        for reg_root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for reg_path in reg_paths:
                try:
                    key = winreg.OpenKey(reg_root, reg_path)
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        subkey_name = winreg.EnumKey(key, i)
                        if name.lower() in subkey_name.lower():
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                path, _ = winreg.QueryValueEx(subkey, "")
                                if path and os.path.exists(path):
                                    return path
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _find_store_app(name: str) -> Optional[str]:
    """Check for Windows Store app by trying to launch it."""
    # Some common store apps
    store_schemes = {
        "spotify":      "spotify:",
        "netflix":      "netflix:",
        "whatsapp":     "whatsapp:",
        "prime video":  "primevideo:",
        "xbox":         "ms-xbox:",
        "xbox app":     "ms-xbox:",
        "photos":       "ms-photos:",
        "weather":      "bingweather:",
        "news":         "bingnews:",
        "maps":         "bingmaps:",
        "mail":         "ms-outlookmobile:",
        "calendar":     "outlookcal:",
        "store":        "ms-windows-store:",
    }
    nl = name.lower()
    for k, v in store_schemes.items():
        if nl in k or k in nl:
            return v
    return None


def get_all_installed_apps() -> Dict[str, str]:
    """
    Scan all locations and return {app_name: exe_path} for every found app.
    Takes a few seconds but gives a complete picture.
    """
    found: Dict[str, str] = {}

    # System commands
    found.update(SYSTEM_COMMANDS)

    # Known paths
    for name, paths in KNOWN_PATHS.items():
        for p in paths:
            p = os.path.expandvars(str(p))
            if os.path.exists(p):
                found[name] = p
                break

    # Scan filesystem
    for root in SEARCH_ROOTS[:5]:  # Limit scan to top 5 roots for speed
        root = os.path.expandvars(root)
        if not os.path.isdir(root):
            continue
        try:
            for p in Path(root).rglob("*.exe"):
                app_name = p.stem.lower().replace("_", " ").replace("-", " ")
                if app_name not in found and len(app_name) > 2:
                    found[app_name] = str(p)
        except (PermissionError, OSError):
            pass

    return found


def launch_app(name: str, args: List[str] = None) -> Tuple[bool, str]:
    """Launch any application by name. Returns (success, message)."""
    key = name.lower().strip()

    # Web fallback first for web-only apps
    if key in WEB_FALLBACKS:
        url = WEB_FALLBACKS[key]
        return _open_in_best_browser(url)

    path = find_app_path(name)

    if path:
        try:
            # ms- scheme (Windows Settings, Store apps)
            if path.startswith("ms-") or ":" in path and len(path) < 30:
                os.startfile(path)
                return True, f"'{name}' khul raha hai, Sir!"

            # .msc files (Microsoft Management Console)
            if path.endswith(".msc") or path.endswith(".cpl"):
                subprocess.Popen(["mmc", path] if path.endswith(".msc") else ["control", path],
                                 shell=True)
                return True, f"'{name}' khul raha hai, Sir!"

            # Regular exe
            cmd = [path] + (args or [])
            subprocess.Popen(cmd, shell=False)
            return True, f"'{name}' khul raha hai, Sir! Path: {path}"

        except Exception as e:
            # Try shell=True as last resort
            try:
                subprocess.Popen(path, shell=True)
                return True, f"'{name}' khula (shell mode), Sir!"
            except Exception as e2:
                return False, f"'{name}' open nahi hua: {e2}"

    # Partial name search in known paths
    for k, paths in KNOWN_PATHS.items():
        if key in k or k in key:
            for p in paths:
                p = os.path.expandvars(str(p))
                if os.path.exists(p):
                    try:
                        subprocess.Popen([p], shell=False)
                        return True, f"'{k}' khul raha hai, Sir!"
                    except Exception:
                        pass

    return (False,
        f"Sir, '{name}' laptop pe nahi mila. "
        f"Yeh install hai? Agar nahi hai toh main research kar ke "
        f"best free alternative bata sakta hoon.")


def _open_in_best_browser(url: str) -> Tuple[bool, str]:
    """Open URL in best available browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    chrome_path = KNOWN_PATHS.get("chrome", [])
    for p in chrome_path:
        p = os.path.expandvars(str(p))
        if os.path.exists(p):
            try:
                subprocess.Popen([p, url], shell=False)
                return True, f"Chrome mein {url} khul raha hai, Sir!"
            except Exception:
                pass
    try:
        webbrowser.open(url)
        return True, f"Browser mein {url} khula, Sir!"
    except Exception as e:
        return False, f"Browser error: {e}"


def close_app_by_name(name: str) -> Tuple[bool, str]:
    """Close any running application by name."""
    killed = []

    # Try pygetwindow
    if PYGETWINDOW:
        try:
            wins = gw.getWindowsWithTitle(name)
            for w in wins:
                try:
                    w.close()
                    killed.append(w.title)
                except Exception:
                    pass
        except Exception:
            pass

    # Try psutil
    if PSUTIL:
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                pname = proc.info.get("name", "").lower()
                if name.lower() in pname or pname in name.lower():
                    proc.kill()
                    killed.append(proc.info["name"])
        except Exception:
            pass

    # Try taskkill
    if not killed:
        exe = name if name.endswith(".exe") else name + ".exe"
        r = subprocess.run(
            f'taskkill /f /im "{exe}"',
            shell=True, capture_output=True, text=True
        )
        if r.returncode == 0:
            killed.append(name)

    if killed:
        return True, f"Band kiya: {', '.join(set(killed))}"
    return False, f"'{name}' running nahi mila"


def get_running_apps() -> List[str]:
    """Get list of currently running application names."""
    apps = []
    if PYGETWINDOW:
        try:
            apps = [w.title for w in gw.getAllWindows() if w.title.strip()]
        except Exception:
            pass
    if not apps and PSUTIL:
        try:
            apps = list({p.info["name"]
                         for p in psutil.process_iter(["name"])
                         if p.info["name"]})
        except Exception:
            pass
    return apps[:30]

