"""
speech/stt_engine.py — JARVIS OMEGA V10  ★ FIXED ★
FIXES:
  1. Groq API key requirement removed — works 100% FREE now
  2. Primary: Google Speech Recognition (free, no key needed)
  3. Fallback: Local Whisper (if installed)
  4. sounddevice + numpy used for recording (Python 3.14 compatible)
  5. PyAudio NOT used (broken on Python 3.14)
  6. Hindi → English translation preserved
  7. Microphone calibration on startup
  8. is_listening flag properly managed
"""
from __future__ import annotations

import io, os, re, time, wave, queue, threading, tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

BASE = Path(__file__).resolve().parent.parent

# ── sounddevice (Python 3.14 compatible, no PyAudio) ─────────────────────────
try:
    import sounddevice as sd
    import numpy as np
    SD = True
except ImportError:
    SD = False
    print("[STT] ✗ sounddevice missing — pip install sounddevice numpy")

# ── Google Speech Recognition (FREE — no API key) ────────────────────────────
try:
    import speech_recognition as sr
    SR_LIB = True
except ImportError:
    SR_LIB = False
    print("[STT] ⚠ SpeechRecognition not installed — pip install SpeechRecognition")

# ── Local Whisper (optional, offline) ────────────────────────────────────────
try:
    import whisper as _whisper
    LOCAL_WHISPER = True
except ImportError:
    LOCAL_WHISPER = False


# ══════════════════════════════════════════════════════════════════════════════
# HINDI → ENGLISH TRANSLATION MAP
# ══════════════════════════════════════════════════════════════════════════════
_HINDI_TO_ENGLISH = {
    'खोलो':'open','खोल':'open','बंद':'close','बंद करो':'close',
    'यूट्यूब':'youtube','गूगल':'google','क्रोम':'chrome',
    'नोटपैड':'notepad','स्पॉटिफाई':'spotify','व्हाट्सएप':'whatsapp',
    'सर्च':'search','खोज':'search','चलाओ':'play','बजाओ':'play',
    'स्क्रीनशॉट':'screenshot','वॉल्यूम':'volume',
    'बढ़ाओ':'up','कम':'down','म्यूट':'mute','टाइप':'type',
    'ऊपर':'up','नीचे':'down','क्लिक':'click',
    'मैं':'i','तुम':'you','करो':'do','दिखाओ':'show',
    'क्या':'what','कैसे':'how','कहाँ':'where',
    'है':'is','और':'and','या':'or',
    'अच्छा':'good','ठीक':'ok','धन्यवाद':'thanks',
    'हाँ':'yes','नहीं':'no','अभी':'now',
    'हैलो':'hello','हेलो':'hello','जार्विस':'jarvis',
}


def _translate_hindi(text: str) -> str:
    """FIX V12: \b word boundaries FAIL on Devanagari — use str.replace() instead."""
    if not re.search(r'[\u0900-\u097F]', text):
        return text
    for hi, en in _HINDI_TO_ENGLISH.items():
        text = text.replace(hi, en)        # simple replace — works on Unicode
    text = re.sub(r'[\u0900-\u097F]+', ' ', text)   # strip untranslated chars
    result = re.sub(r'\s+', ' ', text).strip()
    return result if result else text       # never return empty if input had content


# ══════════════════════════════════════════════════════════════════════════════
# STT CORRECTIONS (common mishears)
# ══════════════════════════════════════════════════════════════════════════════
_CORRECTIONS = {
    r'\bkrome\b':         'chrome',
    r'\bchrom\b':         'chrome',
    r'\byou tube\b':      'youtube',
    r'\bwatsapp\b':       'whatsapp',
    r'\bspotify\b':       'spotify',
    r'\bvs code\b':       'vscode',
    r'\bvisual studio\b': 'vscode',
    r'\bkholo\b':         'open',
    r'\bband karo\b':     'close',
    r'\bdhundo\b':        'search',
    r'\bkhojo\b':         'search',
    r'\bbajao\b':         'play music',
    r'\bopen the\b':      'open',
    r'\bclose the\b':     'close',
    r'\bsearch for\b':    'search',
    r'\blook up\b':       'search',
    r'\bgo to\b':         'open',
    r'\bum+\b':           '',
    r'\buh+\b':           '',
}


def _correct(text: str) -> str:
    t = text.lower().strip()
    for pat, rep in _CORRECTIONS.items():
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[0].upper() + t[1:] if t else text


# ══════════════════════════════════════════════════════════════════════════════
# RECORDER  (sounddevice — Python 3.14 compatible)
# ══════════════════════════════════════════════════════════════════════════════
class Recorder:
    SR    = 16000
    CH    = 1
    DTYPE = "int16"
    CHUNK = 512

    SPEECH_THRESH   = 600
    SILENCE_SECS    = 0.7
    MIN_SPEECH_SECS = 0.35
    MAX_SECS        = 12.0

    def record(self) -> Optional[bytes]:
        if not SD:
            return None

        q: queue.Queue = queue.Queue()
        frames = []
        speech_started = False
        silent_chunks  = 0

        sil_needed  = int(self.SILENCE_SECS    * self.SR / self.CHUNK)
        min_speech  = int(self.MIN_SPEECH_SECS * self.SR / self.CHUNK)
        max_chunks  = int(self.MAX_SECS        * self.SR / self.CHUNK)

        def _cb(indata, n, t, status):
            q.put(indata.copy())

        try:
            with sd.InputStream(samplerate=self.SR, channels=self.CH,
                                dtype=self.DTYPE, blocksize=self.CHUNK,
                                callback=_cb):
                for _ in range(max_chunks):
                    try:
                        chunk = q.get(timeout=1.0)
                    except queue.Empty:
                        break
                    frames.append(chunk)
                    amp = np.abs(chunk).mean()
                    if amp > self.SPEECH_THRESH:
                        speech_started = True
                        silent_chunks  = 0
                    elif speech_started:
                        silent_chunks += 1
                        if silent_chunks >= sil_needed:
                            break
        except Exception as e:
            print(f"[STT] record error: {e}")
            return None

        if not speech_started or len(frames) < min_speech:
            return None

        audio = np.concatenate(frames, axis=0)
        return self._to_wav(audio)

    @staticmethod
    def _to_wav(data: "np.ndarray") -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(data.tobytes())
        return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE STT  (FREE — no key needed, needs internet)
# ══════════════════════════════════════════════════════════════════════════════
class GoogleSTT:
    def __init__(self):
        if SR_LIB:
            self._rec = sr.Recognizer()
            print("[STT] ✓ Google STT ready (free, no key)")
        else:
            self._rec = None

    def transcribe(self, wav_bytes: bytes,
                   languages: list[str] | None = None) -> Optional[str]:
        if not self._rec or not SR_LIB:
            return None
        if languages is None:
            languages = ["hi-IN", "en-IN", "en-US"]

        try:
            audio = sr.AudioData(wav_bytes, 16000, 2)
            # Try each language
            for lang in languages:
                try:
                    text = self._rec.recognize_google(audio, language=lang)
                    if text and text.strip():
                        print(f"[STT-GOOGLE] Recognised ({lang}): {text}")
                        return text.strip()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    print(f"[STT-GOOGLE] Request error: {e}")
                    break
        except Exception as e:
            print(f"[STT-GOOGLE] error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL WHISPER  (offline fallback)
# ══════════════════════════════════════════════════════════════════════════════
class LocalWhisper:
    def __init__(self, model_name: str = "tiny"):
        self.model = None
        if LOCAL_WHISPER:
            try:
                print(f"[STT] Loading local Whisper '{model_name}'…")
                self.model = _whisper.load_model(model_name)
                print(f"[STT] ✓ Local Whisper '{model_name}' loaded")
            except Exception as e:
                print(f"[STT] Local Whisper load error: {e}")

    def transcribe(self, wav_bytes: bytes) -> Optional[str]:
        if not self.model:
            return None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp = f.name
            with wave.open(tmp, 'rb') as wf:
                if wf.getnframes() < 100:
                    os.unlink(tmp)
                    return None
            result = self.model.transcribe(tmp, fp16=False, task="transcribe")
            os.unlink(tmp)
            return (result.get("text") or "").strip() or None
        except Exception as e:
            if "0 elements" not in str(e) and "reshape" not in str(e):
                print(f"[STT-LOCAL] transcribe error: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN STT ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class STTEngine(QObject):
    """
    Speech-to-text for Python 3.14 — no PyAudio needed.
    Uses sounddevice for recording.
    FREE: Google STT (no key) → Local Whisper fallback.
    """
    text_ready        = pyqtSignal(str)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()
    error_occurred    = pyqtSignal(str)

    WAKE_WORDS = ["jarvis", "hey jarvis", "ok jarvis", "j.a.r.v.i.s"]

    def __init__(self, settings: dict):
        super().__init__()
        self.settings    = settings
        self.is_listening = False
        self._rec        = None
        self._google     = None
        self._local      = None
        self._init()

    def _init(self):
        if not SD:
            print("[STT] ✗ sounddevice unavailable — voice input disabled")
            return

        self._rec = Recorder()
        print("[STT] ✓ Recorder ready (sounddevice, no PyAudio)")

        # Google STT (free, primary)
        self._google = GoogleSTT()

        # Local Whisper (offline fallback, loads in background)
        if LOCAL_WHISPER:
            model_name = self.settings.get("whisper_model", "tiny")
            threading.Thread(
                target=self._load_whisper,
                args=(model_name,), daemon=True
            ).start()

        # Calibrate microphone in background
        threading.Thread(target=self.calibrate, daemon=True).start()

    def _load_whisper(self, name: str):
        self._local = LocalWhisper(name)

    def calibrate(self, duration: float = 1.2):
        """Auto-calibrate noise threshold."""
        if not SD or not self._rec:
            return
        try:
            q: queue.Queue = queue.Queue()
            samples = []
            max_s = int(duration * 16000 / 512)

            def _cb(indata, n, t, status):
                q.put(indata.copy())

            with sd.InputStream(samplerate=16000, channels=1,
                               dtype="int16", blocksize=512, callback=_cb):
                for _ in range(max_s):
                    try:
                        chunk = q.get(timeout=1.0)
                        samples.append(np.abs(chunk).mean())
                    except queue.Empty:
                        break

            if samples:
                noise = np.mean(samples)
                thresh = max(350, int(noise * 3.5))
                self._rec.SPEECH_THRESH = thresh
                print(f"[STT] Calibrated — noise={noise:.0f}, threshold={thresh}")
        except Exception as e:
            print(f"[STT] Calibration error: {e}")

    def listen_once(self, timeout: float = 5.0,
                    phrase_limit: float = 10.0) -> Optional[str]:
        if not SD or not self._rec:
            return None
        try:
            print("[STT] Listening…")
            wav = self._rec.record()
            if wav is None:
                print("[STT] No speech detected")
                return None

            text = self._transcribe(wav)
            if text:
                text = _translate_hindi(text)
                text = _correct(text)
                text = self._strip_wake(text)
                print(f"[STT] ✓ '{text}'")
                return text if text.strip() else None
        except Exception as e:
            print(f"[STT] listen_once error: {e}")
        return None

    def _transcribe(self, wav: bytes) -> Optional[str]:
        # 1. Google STT (free, primary)
        if self._google:
            langs = self.settings.get("stt_fallback_langs", ["hi-IN", "en-IN", "en-US"])
            t = self._google.transcribe(wav, languages=langs)
            if t:
                return t

        # 2. Local Whisper (offline fallback)
        if self._local and self._local.model:
            t = self._local.transcribe(wav)
            if t:
                return t

        return None

    def _strip_wake(self, text: str) -> str:
        """FIX V12: never return empty; handle 'hello jarvis' as greeting."""
        t   = text.strip()
        low = t.lower()
        # Greeting + name: "hello jarvis" → "hello"
        for g in ["hello jarvis", "hi jarvis", "namaste jarvis", "helo jarvis"]:
            if low == g:
                return "hello"
            if low.startswith(g + " ") or low.startswith(g + ","):
                remainder = t[len(g):].strip().lstrip(", ")
                return remainder if remainder else "hello"
        # Command + name: "jarvis open chrome" → "open chrome"
        for ww in ["hey jarvis, ", "hey jarvis ", "ok jarvis, ", "ok jarvis ",
                   "jarvis, ", "jarvis "]:
            if low.startswith(ww):
                remainder = t[len(ww):].strip().lstrip(", ")
                return remainder if remainder else t
        return t

    def start_listening(self):
        if self.is_listening or not SD:
            return
        self.is_listening = True
        self.listening_started.emit()
        threading.Thread(
            target=self._listen_loop, daemon=True, name="jarvis-stt"
        ).start()
        print("[STT] Continuous listening started")

    def stop_listening(self):
        self.is_listening = False
        self.listening_stopped.emit()
        print("[STT] Stopped")

    def _listen_loop(self):
        while self.is_listening:
            text = self.listen_once()
            if text and text.strip():
                self.text_ready.emit(text)
            time.sleep(0.05)
