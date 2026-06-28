"""
speech/tts_engine.py — JARVIS OMEGA V10  ★ FIXED ★
FIXES:
  1. pygame removed — not compatible with Python 3.14
  2. playsound removed — broken on Python 3.14 (uses deprecated imp module)
  3. Audio playback now uses subprocess + Windows built-in (PowerShell/wmplayer)
     with winsound fallback for WAV, and os.startfile for MP3
  4. edge_tts saves MP3 then plays via PowerShell (no extra deps needed)
  5. pyttsx3 works as fully offline fallback
  6. Non-blocking queue-based design preserved
  7. Python 3.14 safe — no deprecated imports
"""
from __future__ import annotations

import asyncio, os, re, queue, threading, tempfile, time, subprocess, platform
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent

# ── TTS backends ──────────────────────────────────────────────────────────────
try:
    import edge_tts
    EDGE = True
except ImportError:
    EDGE = False
    print("[TTS] edge_tts not installed — run: pip install edge-tts")

try:
    import pyttsx3
    PYTTSX = True
except ImportError:
    PYTTSX = False
    print("[TTS] pyttsx3 not installed — run: pip install pyttsx3")


# ══════════════════════════════════════════════════════════════════════════════
# TEXT CLEANER  (strip Devanagari + markdown before speaking)
# ══════════════════════════════════════════════════════════════════════════════
def _clean_for_tts(text: str) -> str:
    # Remove JSON action blocks
    text = re.sub(r'\{[^{}]*?"action"[^{}]*?\}', '', text, flags=re.DOTALL)
    # Remove markdown
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove Devanagari
    text = re.sub(r'[\u0900-\u097F]+', '', text)
    # Remove bracket-wrapped leftovers like [...]
    text = re.sub(r'\[[^\]]*\]', '', text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate to ~350 chars
    if len(text) > 350:
        cut = text[:350].rfind('.')
        text = text[:cut + 1] if cut > 150 else text[:350] + '…'
    return text


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO PLAYBACK  ★ FIXED — no pygame/playsound ★
# Uses Windows PowerShell (built-in) to play MP3/WAV without extra packages
# ══════════════════════════════════════════════════════════════════════════════
def _play_audio(path: str):
    """Play audio file on Windows without pygame or playsound."""
    path = os.path.abspath(path)
    sys = platform.system()

    if sys == "Windows":
        # WAV → winsound (built-in, synchronous, reliable)
        if path.lower().endswith('.wav'):
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                return
            except Exception as e:
                print(f"[TTS] winsound error: {e}")

        # MP3 → PowerShell MediaPlayer (built-in on Windows 10/11)
        try:
            ps_cmd = (
                f"$player = New-Object System.Windows.Media.MediaPlayer; "
                f"$player.Open([uri]'{path}'); "
                f"$player.Play(); "
                f"Start-Sleep -Milliseconds ($player.NaturalDuration.TimeSpan.TotalMilliseconds + 500); "
                f"$player.Close()"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                timeout=60, capture_output=True
            )
            if result.returncode == 0:
                return
        except Exception as e:
            print(f"[TTS] PowerShell MediaPlayer error: {e}")

        # MP3 fallback → wmplayer silent mode
        try:
            proc = subprocess.Popen(
                ["wmplayer", "/play", "/close", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            proc.wait(timeout=30)
            return
        except Exception:
            pass

        # Last resort: open with default app (will open media player UI)
        try:
            os.startfile(path)
            time.sleep(3)  # crude wait
        except Exception as e:
            print(f"[TTS] os.startfile error: {e}")

    elif sys == "Darwin":
        try:
            subprocess.run(["afplay", path], timeout=60)
        except Exception as e:
            print(f"[TTS] afplay error: {e}")
    else:
        for player in ["mpg123", "mpg321", "aplay", "ffplay"]:
            try:
                subprocess.run([player, "-q", path], timeout=60)
                return
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"[TTS] {player} error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# EDGE TTS  (primary — good Indian English voice, needs internet)
# ══════════════════════════════════════════════════════════════════════════════
async def _edge_speak_async(text: str, voice: str, rate: str, pitch: str):
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(tmp.name)
        _play_audio(tmp.name)
    except Exception as e:
        print(f"[TTS-EDGE] async error: {e}")
        raise
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _edge_speak_thread(text: str, voice: str, rate: str, pitch: str):
    """Run Edge TTS in a fresh event loop (safe from Qt thread)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_edge_speak_async(text, voice, rate, pitch))
        loop.close()
    except Exception as e:
        print(f"[TTS-EDGE] thread error: {e}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# PYTTSX3  (offline fallback — works without internet)
# ══════════════════════════════════════════════════════════════════════════════
_pyttsx_engine = None
_pyttsx_lock   = threading.Lock()


def _pyttsx_speak(text: str, rate: int = 170):
    global _pyttsx_engine
    with _pyttsx_lock:
        try:
            if _pyttsx_engine is None:
                _pyttsx_engine = pyttsx3.init()
                voices = _pyttsx_engine.getProperty('voices')
                for v in voices:
                    nm = (v.name or "").lower()
                    vi = (v.id or "").lower()
                    if 'india' in nm or 'prabhat' in nm or 'en-in' in vi:
                        _pyttsx_engine.setProperty('voice', v.id)
                        break
            _pyttsx_engine.setProperty('rate',   rate)
            _pyttsx_engine.setProperty('volume', 0.95)
            _pyttsx_engine.say(text)
            _pyttsx_engine.runAndWait()
        except Exception as e:
            print(f"[TTS-PYTTSX] error: {e}")
            # Reset engine on error so next call re-initializes
            _pyttsx_engine = None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TTS ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class TTSEngine:
    """
    Non-blocking TTS with queue.
    speak(text) returns immediately — audio plays in background thread.
    Primary: Edge TTS (internet required, Indian English voice)
    Fallback: pyttsx3 (offline, built-in Windows voices)
    """

    def __init__(self, settings: dict):
        self.settings    = settings
        self.voice       = settings.get("tts_voice",      "en-IN-PrabhatNeural")
        self.rate        = settings.get("tts_edge_rate",  "+5%")
        self.pitch       = settings.get("tts_edge_pitch", "+0Hz")
        self.pyttsx_rate = settings.get("tts_rate",       175)
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._speaking   = threading.Event()
        self._stop_flag  = threading.Event()
        self._thread     = threading.Thread(
            target=self._worker, daemon=True, name="jarvis-tts")
        self._thread.start()

        mode = "EdgeTTS" if EDGE else ("pyttsx3" if PYTTSX else "NONE")
        print(f"[TTS] ✓ Engine: {mode} | Voice: {self.voice}")
        if not EDGE and not PYTTSX:
            print("[TTS] ⚠ No TTS installed — pip install edge-tts pyttsx3")

    def speak(self, text: str):
        """Non-blocking. Queue text for speaking."""
        clean = _clean_for_tts(text)
        if clean:
            self._queue.put(clean)

    def speak_sync(self, text: str, timeout: float = 30.0):
        """Blocking speak — waits until audio finishes."""
        self.speak(text)
        time.sleep(0.3)
        deadline = time.time() + timeout
        while (not self._queue.empty() or self._speaking.is_set()) \
                and time.time() < deadline:
            time.sleep(0.1)

    def stop(self):
        """Clear queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def set_voice(self, voice_name: str):
        self.voice = voice_name

    def set_rate(self, rate: str):
        self.rate = rate

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def _worker(self):
        while not self._stop_flag.is_set():
            try:
                text = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if text is None:
                break
            self._speaking.set()
            try:
                self._speak_one(text)
            except Exception as e:
                print(f"[TTS] worker error: {e}")
            finally:
                self._speaking.clear()
                self._queue.task_done()

    def _speak_one(self, text: str):
        """Try Edge TTS first, fall back to pyttsx3."""
        if EDGE:
            try:
                _edge_speak_thread(text, self.voice, self.rate, self.pitch)
                return
            except Exception as e:
                print(f"[TTS] Edge failed ({e}), trying pyttsx3…")

        if PYTTSX:
            _pyttsx_speak(text, rate=self.pyttsx_rate)
            return

        print(f"[TTS] No TTS available — text was: {text[:60]}")
