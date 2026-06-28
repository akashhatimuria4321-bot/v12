"""
gui/main_window.py — JARVIS OMEGA V12

V12 FIXES:
  1. ESC — shows ONLY the ball widget; main window made transparent/hidden
     so no black screen covers the desktop.
  2. Ball size: 52×52px (reduced from 60px)
  3. SPACE toggles listening. Press once → start listening, press again → stop.
  4. Ball glow colors:
       ORANGE  → listening (microphone active)
       GREEN   → working / thinking / speaking
       BLUE    → task done / idle
  5. AI speaks back after every response (not just chat).
  6. Chrome-based research for real-time web info.
  7. Multi-step task chaining via ActionChain in brain.
  8. Logical context memory (last app opened is remembered).
"""
from __future__ import annotations

import sys
import math
import random
import time
import threading
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QFrame, QScrollArea,
    QApplication, QSystemTrayIcon, QMenu, QSizePolicy,
    QDialog, QDialogButtonBox, QCheckBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QRect, QPointF,
    QPoint, QSize, QMetaObject, Q_ARG
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QPixmap, QIcon, QKeySequence, QShortcut,
    QTextCursor, QTextCharFormat, QRegion
)

BASE = Path(__file__).resolve().parent.parent

# ── Palette ───────────────────────────────────────────────────────────────────
C_CYAN   = QColor(0, 210, 255)
C_GREEN  = QColor(0, 255, 140)
C_ORANGE = QColor(255, 165, 30)
C_BLUE   = QColor(60, 140, 255)
C_RED    = QColor(255, 60, 60)
C_BG     = QColor(3, 7, 20)
C_PANEL  = QColor(7, 13, 28)
C_TEXT   = QColor(185, 215, 240)
C_MUTED  = QColor(60, 90, 110)
C_ACCENT = QColor(0, 212, 255)

_PANEL_SS = """
QFrame {{
    background: rgba(7,13,28,{alpha});
    border: 1px solid rgba(0,200,255,{border});
    border-radius: 14px;
}}
QTextEdit {{
    background: transparent; color: #b8d4ee;
    font-family: 'Segoe UI'; font-size: 12px; border: none; padding: 6px;
}}
QLineEdit {{
    background: rgba(0,20,50,100); color: #9ec8ef;
    font-family: 'Segoe UI'; font-size: 12px;
    border: 1px solid rgba(0,200,255,55); border-radius: 8px; padding: 6px 10px;
}}
QLineEdit:focus {{ border: 1px solid rgba(0,220,255,130); }}
QPushButton {{
    background: rgba(0,120,180,120); color: #ffffff;
    font-family: 'Segoe UI'; font-size: 11px; font-weight: bold;
    border: none; border-radius: 8px; padding: 6px 14px;
}}
QPushButton:hover {{ background: rgba(0,160,220,180); }}
QPushButton:pressed {{ background: rgba(0,100,150,200); }}
QLabel {{ background: transparent; }}
QScrollBar:vertical {{
    background: rgba(0,0,0,0); width: 5px;
}}
QScrollBar::handle:vertical {{
    background: rgba(0,180,240,50); border-radius: 2px;
}}
QCheckBox {{ color: #b8d4ee; spacing: 6px; font-size: 11px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid rgba(0,200,255,80); }}
QCheckBox::indicator:checked {{ background: rgba(0,200,255,120); }}
"""

def _pss(alpha: int, border: int) -> str:
    return _PANEL_SS.format(alpha=alpha, border=border)


# ═══════════════════════════════════════════════════════════════════════════
# STARFIELD BACKGROUND
# ═══════════════════════════════════════════════════════════════════════════
class _Star:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.reset()

    def reset(self):
        self.x     = random.randint(0, max(self.w, 1))
        self.y     = random.randint(0, max(self.h, 1))
        self.size  = random.uniform(0.4, 2.0)
        self.speed = random.uniform(0.08, 0.4)
        self.base  = random.randint(35, 140)
        self.phase = random.uniform(0, 6.28)
        self.dt    = random.uniform(0.02, 0.05)

    def step(self):
        self.y -= self.speed
        self.phase = (self.phase + self.dt) % 6.28
        if self.y < 0:
            self.y = self.h

    @property
    def alpha(self) -> int:
        return max(0, min(255, int(self.base * (0.5 + 0.5 * math.sin(self.phase)))))


class StarfieldWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._stars: list[_Star] = []
        QTimer(self, timeout=self._tick, interval=18).start()

    def _tick(self):
        w, h = self.width(), self.height()
        if not self._stars and w > 10:
            self._stars = [_Star(w, h) for _ in range(160)]
        for s in self._stars:
            s.w, s.h = w, h
            s.step()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(3, 7, 20))
        g.setColorAt(0.5, QColor(5, 11, 26))
        g.setColorAt(1.0, QColor(3, 7, 20))
        p.fillRect(self.rect(), g)
        for s in self._stars:
            p.setPen(QPen(QColor(160, 210, 255, s.alpha), s.size))
            p.drawPoint(int(s.x), int(s.y))
        v = QRadialGradient(w / 2, h / 2, max(w, h) * 0.65)
        v.setColorAt(0.0, QColor(0, 0, 0, 0))
        v.setColorAt(1.0, QColor(0, 0, 0, 170))
        p.fillRect(self.rect(), v)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════
# ARC REACTOR (Center JARVIS Logo)
# ═══════════════════════════════════════════════════════════════════════════
class ArcReactor(QWidget):
    def __init__(self, parent=None, size=200):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size, size)
        self._angle = 0.0
        self._pulse = 0.0
        self._mode  = "idle"
        QTimer(self, timeout=self._tick, interval=15).start()

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def _tick(self):
        speeds = {"idle": 1.8, "listening": 4.5, "thinking": 6.0, "speaking": 5.0}
        self._angle = (self._angle + speeds.get(self._mode, 2.0)) % 360
        self._pulse = (self._pulse + 0.07) % 6.28
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = self.width() // 2
        OR = cx - 8
        IR = int(OR * 0.64)
        pf = 0.82 + 0.18 * math.sin(self._pulse)

        colours = {
            "idle":      C_CYAN,
            "listening": C_ORANGE,
            "thinking":  C_GREEN,
            "speaking":  C_GREEN,
            "done":      C_BLUE,
        }
        ring_col = colours.get(self._mode, C_CYAN)

        for i in range(8, 0, -1):
            alpha = int(22 * pf / i)
            p.setPen(QPen(QColor(0, 200, 255, alpha), i * 3))
            p.drawEllipse(cx - OR, cy - OR, OR * 2, OR * 2)

        p.setPen(QPen(ring_col, 2.5))
        p.drawEllipse(cx - OR, cy - OR, OR * 2, OR * 2)

        p.setPen(QPen(QColor(0, 235, 255, 255), 4,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(cx - OR + 3, cy - OR + 3, (OR - 3) * 2, (OR - 3) * 2,
                  int(self._angle * 16), int(115 * 16))

        p.setPen(QPen(QColor(60, 180, 255, 110), 2.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(cx - OR + 8, cy - OR + 8, (OR - 8) * 2, (OR - 8) * 2,
                  int(-self._angle * 1.6 * 16), int(75 * 16))

        p.setPen(QPen(QColor(0, 170, 210, 80), 1.5))
        p.drawEllipse(cx - IR, cy - IR, IR * 2, IR * 2)

        dot_r = 5.5 * pf
        p.setBrush(QBrush(ring_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(float(cx), float(cy)), dot_r, dot_r)

        labels = {
            "idle":      "JARVIS",
            "listening": "LISTENING",
            "thinking":  "THINKING",
            "speaking":  "SPEAKING",
            "done":      "DONE",
        }
        lbl = labels.get(self._mode, "JARVIS")
        f = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QPen(QColor(190, 225, 255, 200)))
        tw = p.fontMetrics().horizontalAdvance(lbl)
        p.drawText(cx - tw // 2, cy + 6, lbl)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════
# CLOCK + DATE
# ═══════════════════════════════════════════════════════════════════════════
class ClockLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "color:#9ec8ef; font-family:'Segoe UI',monospace;"
            "font-size:52px; font-weight:200; letter-spacing:6px; background:transparent;")
        QTimer(self, timeout=self._tick, interval=1000).start()
        self._tick()

    def _tick(self):
        self.setText(datetime.now().strftime("%H:%M"))


class DateLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "color:#3a5868; font-family:'Segoe UI'; font-size:10px;"
            "letter-spacing:3px; background:transparent;")
        QTimer(self, timeout=self._tick, interval=60000).start()
        self._tick()

    def _tick(self):
        self.setText(datetime.now().strftime("%A, %d %B %Y").upper())


# ═══════════════════════════════════════════════════════════════════════════
# STATUS BAR
# ═══════════════════════════════════════════════════════════════════════════
class StatusBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setStyleSheet(
            "QFrame{background:rgba(0,5,18,180);border-top:1px solid rgba(0,200,255,25);}"
            "QLabel{color:#3a5060;font-family:'Segoe UI';font-size:10px;background:transparent;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        self.left = QLabel("SYSTEM ONLINE")
        self.left.setStyleSheet("color:#00c0ef; background:transparent;")
        lay.addWidget(self.left)
        lay.addStretch()
        lay.addWidget(QLabel("JARVIS OMEGA V12"))
        lay.addStretch()
        self.right = QLabel("READY")
        lay.addWidget(self.right)

    def set(self, text: str, kind: str = "normal"):
        self.right.setText(text.upper())
        c = {"error": "#ff4040", "success": "#30ff80", "warning": "#ffaa00"}.get(kind, "#3a5060")
        self.right.setStyleSheet(f"color:{c};background:transparent;")


# ═══════════════════════════════════════════════════════════════════════════
# CHAT PANEL (RIGHT SIDE)
# ═══════════════════════════════════════════════════════════════════════════
class ChatPanel(QFrame):
    command_entered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._alpha = 0
        self._apply(0, 0)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hdr = QLabel("◈ JARVIS V12 INTERFACE ◈")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet(
            "color:#00c0ef;font-family:'Segoe UI';font-size:10px;"
            "font-weight:bold;letter-spacing:4px;background:transparent;")
        lay.addWidget(hdr)

        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.document().setMaximumBlockCount(400)
        self.display.setFont(QFont("Segoe UI", 12))
        lay.addWidget(self.display)

        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Type or press SPACE to speak | SPACE again to stop…")
        self.inp.returnPressed.connect(self._send)
        row.addWidget(self.inp)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedWidth(46)
        self.mic_btn.setToolTip("Toggle voice listening")
        row.addWidget(self.mic_btn)

        self.send_btn = QPushButton("SEND")
        self.send_btn.setFixedWidth(58)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

    def _apply(self, alpha: int, border: int):
        self._alpha = alpha
        self.setStyleSheet(_pss(alpha, border))

    def show_panel(self):
        self.setVisible(True)
        self.raise_()
        self._fade_to(175)

    def hide_panel(self):
        self._fade_to(0)

    def _fade_to(self, target: int):
        if hasattr(self, "_ft") and self._ft.isActive():
            self._ft.stop()
        self._ft_target = target
        self._ft = QTimer(self)
        self._ft.timeout.connect(self._do_fade)
        self._ft.start(12)

    def _do_fade(self):
        step = 14 if self._ft_target > self._alpha else -14
        v = self._alpha + step
        v = max(0, min(175, v))
        border = int(v * 55 / 175)
        self._apply(v, border)
        if v == 0:
            self._ft.stop()
            self.setVisible(False)
        elif v >= 175:
            self._ft.stop()

    def add_message(self, text: str, sender: str = "JARVIS"):
        ts = datetime.now().strftime("%H:%M:%S")
        if sender == "JARVIS":
            self.display.append(f'[{ts}] 🤖 <b style="color:#00c8ff;">JARVIS:</b> {text}')
        elif sender == "USER":
            self.display.append(f'[{ts}] 🧑 <b style="color:#55ee88;">Sir:</b> {text}')
        elif sender == "ACTION_OK":
            self.display.append(f'[{ts}] ✅ <b style="color:#aaffcc;">{text}</b>')
        elif sender == "ACTION_FAIL":
            self.display.append(f'[{ts}] ❌ <b style="color:#ff8888;">{text}</b>')
        elif sender == "SYSTEM":
            self.display.append(f'[{ts}] ℹ️ <b style="color:#888888;">{text}</b>')
        else:
            self.display.append(f'[{ts}] {sender}: {text}')
        self.display.verticalScrollBar().setValue(
            self.display.verticalScrollBar().maximum())

    def add_listening(self):
        self.add_message("🎙️ Listening… boliye Sir (SPACE dobara dabayein to band karein)", "SYSTEM")

    def add_thinking(self):
        self.add_message("⚙️ Processing…", "SYSTEM")

    def clear(self):
        self.display.clear()

    def _send(self):
        txt = self.inp.text().strip()
        if not txt:
            return
        self.add_message(txt, "USER")
        self.inp.clear()
        self.command_entered.emit(txt)


# ═══════════════════════════════════════════════════════════════════════════
# OUTPUT PANEL (LEFT SIDE)
# ═══════════════════════════════════════════════════════════════════════════
class OutputPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._alpha = 0
        self._hidden_to_top = False
        self._original_height = 440
        self._apply(0, 0)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hdr_row = QHBoxLayout()
        hdr = QLabel("◈ OUTPUT ◈")
        hdr.setStyleSheet(
            "color:#00c0ef;font-family:'Segoe UI';font-size:10px;"
            "font-weight:bold;letter-spacing:4px;background:transparent;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 22)
        close_btn.setStyleSheet(
            "QPushButton{background:rgba(255,60,60,60);color:#ff8080;"
            "font-size:11px;border-radius:5px;}"
            "QPushButton:hover{background:rgba(255,60,60,130);}")
        close_btn.clicked.connect(self.hide_panel)
        hdr_row.addWidget(close_btn)
        lay.addLayout(hdr_row)

        tab_row = QHBoxLayout()
        self._tabs: dict[str, QPushButton] = {}
        for t in ("SCREEN", "IMAGE", "VIDEO", "INFO", "CMD"):
            btn = QPushButton(t)
            btn.setFixedHeight(24)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, name=t: self._switch_tab(name))
            self._tabs[t] = btn
            tab_row.addWidget(btn)
        lay.addLayout(tab_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_lay.setSpacing(6)
        scroll.setWidget(self._content)
        lay.addWidget(scroll)
        self._scroll = scroll

        self.cmd_output = QTextEdit()
        self.cmd_output.setReadOnly(True)
        self.cmd_output.setFont(QFont("Consolas", 11))
        self.cmd_output.setStyleSheet(
            "background:rgba(0,5,15,180); color:#aaffcc; border:none; "
            "border-radius:6px; padding:6px; font-size:11px;")
        self.cmd_output.setMaximumHeight(200)
        self.cmd_output.setVisible(False)
        lay.addWidget(self.cmd_output)

        self._switch_tab("CMD")

    def _apply(self, alpha: int, border: int):
        self._alpha = alpha
        self.setStyleSheet(_pss(alpha, border))

    def _switch_tab(self, name: str):
        for k, btn in self._tabs.items():
            active = k == name
            btn.setChecked(active)
            c = "#00c0ef" if active else "#2a4050"
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{c};"
                f"font-size:10px;font-weight:bold;border:none;"
                f"border-bottom: {'2px solid #00c0ef' if active else 'none'};}}")
        if hasattr(self, "cmd_output") and self.cmd_output:
            self.cmd_output.setVisible(name == "CMD")

    def show_panel(self):
        self.setVisible(True)
        self.raise_()
        self._fade_to(165)

    def hide_panel(self):
        self._fade_to(0)

    def _fade_to(self, target: int):
        if hasattr(self, "_ft") and self._ft.isActive():
            self._ft.stop()
        self._ft_target = target
        self._ft = QTimer(self)
        self._ft.timeout.connect(self._do_fade)
        self._ft.start(12)

    def _do_fade(self):
        step = 14 if self._ft_target > self._alpha else -14
        v = self._alpha + step
        v = max(0, min(165, v))
        border = int(v * 50 / 165)
        self._apply(v, border)
        if v == 0:
            self._ft.stop()
            self.setVisible(False)
        elif v >= 165:
            self._ft.stop()

    def add_text(self, text: str, tab: str = "INFO"):
        self._switch_tab(tab.upper())
        self.show_panel()
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color:#b8d4ee;font-size:12px;font-family:'Segoe UI';"
            "padding:4px;background:transparent;")
        self._content_lay.addWidget(lbl)
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum())

    def add_image(self, path_or_pixmap, caption: str = ""):
        self._switch_tab("IMAGE")
        self.show_panel()
        pm = path_or_pixmap if isinstance(path_or_pixmap, QPixmap) else QPixmap(str(path_or_pixmap))
        if not pm.isNull():
            pm = pm.scaledToWidth(340, Qt.TransformationMode.SmoothTransformation)
            img_lbl = QLabel()
            img_lbl.setPixmap(pm)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._content_lay.addWidget(img_lbl)
            if caption:
                lbl = QLabel(caption)
                lbl.setStyleSheet("color:#5a8090;font-size:10px;background:transparent;")
                self._content_lay.addWidget(lbl)

    def add_cmd(self, text: str, ok: bool = True):
        self._switch_tab("CMD")
        self.show_panel()
        if hasattr(self, "cmd_output") and self.cmd_output:
            color = "#aaffcc" if ok else "#ff8888"
            icon = "✅" if ok else "❌"
            self.cmd_output.append(f'<span style="color:{color};">{icon} {text}</span>')
            self.cmd_output.moveCursor(QTextCursor.MoveOperation.End)

    def clear(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if hasattr(self, "cmd_output") and self.cmd_output:
            self.cmd_output.clear()


# ═══════════════════════════════════════════════════════════════════════════
# V12: ASSISTANT BALL — Small floating ball, NO background window
# Shows ONLY when ESC pressed. Glow: ORANGE=listen, GREEN=working, BLUE=done
# ═══════════════════════════════════════════════════════════════════════════
class AssistantBall(QWidget):
    """
    Standalone top-level window — 52×52px transparent circle.
    Absolutely no background, no black screen.
    Glow ring color = current AI state.
    Draggable. Click to restore full window.
    """
    clicked = pyqtSignal()

    # Ball states → glow color
    STATE_COLORS = {
        "idle":      QColor(60, 140, 255),     # BLUE  – done / ready
        "listening": QColor(255, 165, 30),     # ORANGE – microphone active
        "thinking":  QColor(0, 255, 140),      # GREEN  – working
        "speaking":  QColor(0, 255, 140),      # GREEN  – speaking
        "done":      QColor(60, 140, 255),     # BLUE  – task complete
    }

    BALL_SIZE = 52

    def __init__(self, parent=None):
        # Top-level widget: FramelessWindowHint + Tool → no taskbar entry
        # WA_TranslucentBackground → only the painted content is visible
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(self.BALL_SIZE, self.BALL_SIZE)

        self._angle  = 0.0
        self._pulse  = 0.0
        self._state  = "idle"
        self._drag_pos: Optional[QPoint] = None

        self.setVisible(False)
        QTimer(self, timeout=self._tick, interval=18).start()

        # Position bottom-right by default
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.BALL_SIZE - 20,
                  screen.height() - self.BALL_SIZE - 50)

    # ── Public API ─────────────────────────────────────────────────────────
    def set_state(self, state: str):
        self._state = state
        self.update()

    def show_ball(self):
        self.setVisible(True)
        self.raise_()
        self.activateWindow()

    def hide_ball(self):
        self.setVisible(False)

    # ── Animation ──────────────────────────────────────────────────────────
    def _tick(self):
        speeds = {"idle": 2.5, "listening": 6.0, "thinking": 5.0, "speaking": 4.5}
        self._angle = (self._angle + speeds.get(self._state, 2.5)) % 360
        self._pulse = (self._pulse + 0.1) % 6.28
        if self.isVisible():
            self.update()

    # ── Paint ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sz = self.BALL_SIZE
        cx = cy = sz // 2
        r  = sz // 2 - 4   # 22px radius
        pf = 0.75 + 0.25 * math.sin(self._pulse)

        glow_col = self.STATE_COLORS.get(self._state, QColor(60, 140, 255))

        # ── Outer glow halo ─────────────────────────────────────────────
        halo = QRadialGradient(cx, cy, r + 10)
        halo.setColorAt(0,   QColor(glow_col.red(), glow_col.green(), glow_col.blue(), int(80 * pf)))
        halo.setColorAt(0.5, QColor(glow_col.red(), glow_col.green(), glow_col.blue(), int(30 * pf)))
        halo.setColorAt(1,   QColor(0, 0, 0, 0))
        p.setBrush(QBrush(halo))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - r - 10, cy - r - 10, (r + 10) * 2, (r + 10) * 2)

        # ── Ball body ───────────────────────────────────────────────────
        body = QRadialGradient(cx - 5, cy - 5, r)
        body.setColorAt(0, QColor(18, 55, 100, 230))
        body.setColorAt(1, QColor(4, 12, 28, 220))
        p.setBrush(QBrush(body))
        p.setPen(QPen(glow_col, 2.0))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # ── Spinning arc (glow color) ────────────────────────────────────
        p.setPen(QPen(glow_col, 2.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(cx - r + 4, cy - r + 4, (r - 4) * 2, (r - 4) * 2,
                  int(self._angle * 16), int(100 * 16))

        # ── Centre "J" label ─────────────────────────────────────────────
        f = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QPen(QColor(
            glow_col.red(), glow_col.green(), glow_col.blue(), 230)))
        p.drawText(QRect(0, 0, sz, sz), Qt.AlignmentFlag.AlignCenter, "J")
        p.end()

    # ── Mouse events: drag + click ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Only fire clicked if we didn't drag (small movement)
            if self._drag_pos:
                delta = (e.globalPosition().toPoint() -
                         (self.frameGeometry().topLeft() + self._drag_pos))
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    self.clicked.emit()
            self._drag_pos = None
            e.accept()


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS V12 Settings")
        self.setFixedSize(340, 360)
        self.setStyleSheet(_pss(200, 80))
        self.settings = settings
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        hdr = QLabel("⚡ SETTINGS — V12")
        hdr.setStyleSheet("color:#00c0ef;font-size:14px;font-weight:bold;letter-spacing:3px;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hdr)

        self.hinglish_cb = QCheckBox("Hinglish Display")
        self.hinglish_cb.setChecked(bool(self.settings.get("hinglish_display_mode", True)))
        lay.addWidget(self.hinglish_cb)

        self.tts_cb = QCheckBox("Voice Output (TTS) — AI speaks responses")
        self.tts_cb.setChecked(True)
        lay.addWidget(self.tts_cb)

        self.vision_cb = QCheckBox("Screen Vision (OCR + AI)")
        self.vision_cb.setChecked(bool(self.settings.get("V10_FEATURES", {}).get("vision_enabled", True)))
        lay.addWidget(self.vision_cb)

        self.web_cb = QCheckBox("Web Search (DuckDuckGo fallback)")
        self.web_cb.setChecked(bool(self.settings.get("V10_FEATURES", {}).get("web_search_enabled", True)))
        lay.addWidget(self.web_cb)

        self.chrome_cb = QCheckBox("Chrome Research (real-time info)")
        self.chrome_cb.setChecked(bool(self.settings.get("V10_FEATURES", {}).get("chrome_research_enabled", True)))
        lay.addWidget(self.chrome_cb)

        lay.addStretch()
        model_hdr = QLabel("OLLAMA MODELS")
        model_hdr.setStyleSheet("color:#00c0ef;font-size:10px;font-weight:bold;letter-spacing:2px;")
        lay.addWidget(model_hdr)

        models = self.settings.get("V10_MODELS", {})
        for name, model in models.items():
            row = QHBoxLayout()
            name_lbl = QLabel(name.title())
            name_lbl.setFixedWidth(80)
            name_lbl.setStyleSheet("color:#5a7a9a;font-size:10px;")
            stat_lbl = QLabel(model)
            stat_lbl.setStyleSheet("color:#00ff88;font-size:10px;")
            row.addWidget(name_lbl)
            row.addWidget(stat_lbl)
            row.addStretch()
            lay.addLayout(row)

        lay.addStretch()
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def get_settings(self):
        return {
            "hinglish_display_mode": self.hinglish_cb.isChecked(),
            "tts_enabled":           self.tts_cb.isChecked(),
            "vision_enabled":        self.vision_cb.isChecked(),
            "web_search_enabled":    self.web_cb.isChecked(),
            "chrome_research_enabled": self.chrome_cb.isChecked(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════
class BrainWorker(QThread):
    result_ready   = pyqtSignal(str, list)
    error_occurred = pyqtSignal(str)

    def __init__(self, brain, text: str, task_hint: str = "chat"):
        super().__init__()
        self.brain = brain
        self.text  = text
        self.hint  = task_hint

    def run(self):
        try:
            text, actions = self.brain.process(self.text, self.hint)
            self.result_ready.emit(text, actions)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ListenWorker(QThread):
    recognised = pyqtSignal(str)
    failed     = pyqtSignal()

    def __init__(self, stt):
        super().__init__()
        self.stt = stt

    def run(self):
        try:
            text = self.stt.listen_once(timeout=8.0, phrase_limit=15.0)
            if text:
                self.recognised.emit(text)
            else:
                self.failed.emit()
        except Exception:
            self.failed.emit()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════
class JarvisOmegaWindow(QMainWindow):
    speak_signal        = pyqtSignal(str)
    status_signal       = pyqtSignal(str, str)
    ai_reply_signal     = pyqtSignal(str, list)
    ai_error_signal     = pyqtSignal(str)
    stt_heard_signal    = pyqtSignal(str)
    stt_fail_signal     = pyqtSignal()
    action_chat_signal  = pyqtSignal(str, str)   # (message, kind)
    action_cmd_signal   = pyqtSignal(str, bool)  # (message, ok)
    action_done_signal  = pyqtSignal()           # all actions finished

    def __init__(self, settings: dict):
        super().__init__()
        self.settings   = settings
        self.brain      = None
        self.speaker    = None
        self.listener   = None
        self.automation = None

        # V12 state
        self._hidden          = False   # True = ball mode (no black screen)
        self._listening       = False   # SPACE toggle
        self._worker: Optional[BrainWorker] = None
        self._listen:  Optional[ListenWorker] = None
        self._busy            = False

        self._hinglish_mode          = bool(settings.get("hinglish_display_mode", True))
        self._tts_enabled            = True
        self._vision_enabled         = bool(settings.get("V10_FEATURES", {}).get("vision_enabled", True))
        self._web_search_enabled     = bool(settings.get("V10_FEATURES", {}).get("web_search_enabled", True))
        self._chrome_research        = bool(settings.get("V10_FEATURES", {}).get("chrome_research_enabled", True))

        self._build_window()
        self._build_ui()
        self._setup_shortcuts()
        self._setup_tray()

        self.speak_signal.connect(self._on_speak)
        self.status_signal.connect(lambda t, k: self.statusbar.set(t, k))
        self.ai_reply_signal.connect(self._on_ai_reply)
        self.ai_error_signal.connect(self._on_ai_error)
        self.stt_heard_signal.connect(self._on_stt_heard)
        self.stt_fail_signal.connect(self._on_stt_fail)
        self.action_chat_signal.connect(
            lambda msg, kind: self.chat.add_message(msg, kind))
        self.action_cmd_signal.connect(
            lambda msg, ok: self.output.add_cmd(msg, ok))
        self.action_done_signal.connect(self._on_actions_done)

        QTimer.singleShot(300, self._init_modules)

    # ── Window setup ──────────────────────────────────────────────────────
    def _build_window(self):
        self.setWindowTitle("JARVIS OMEGA V12")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)

        self.starfield = StarfieldWidget(root)
        self.starfield.setGeometry(root.rect())

        self.content = QWidget(root)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content.setGeometry(root.rect())

        c_lay = QVBoxLayout(self.content)
        c_lay.setContentsMargins(40, 60, 40, 40)
        c_lay.addStretch(2)

        centre = QWidget()
        centre.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        cl = QVBoxLayout(centre)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(10)

        self.reactor = ArcReactor(centre, size=200)
        cl.addWidget(self.reactor, alignment=Qt.AlignmentFlag.AlignCenter)

        self.clock = ClockLabel(centre)
        cl.addWidget(self.clock, alignment=Qt.AlignmentFlag.AlignCenter)

        self.date = DateLabel(centre)
        cl.addWidget(self.date, alignment=Qt.AlignmentFlag.AlignCenter)

        self.hint = QLabel("SPACE = Talk | ESC = Ball mode | Ctrl+J = Chat")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hint.setStyleSheet(
            "color:#2a4858;font-family:'Segoe UI';font-size:11px;"
            "letter-spacing:2px;background:transparent;margin-top:18px;")
        cl.addWidget(self.hint)

        c_lay.addWidget(centre, alignment=Qt.AlignmentFlag.AlignCenter)
        c_lay.addStretch(3)

        self.statusbar = StatusBar()
        c_lay.addWidget(self.statusbar)

        # Floating panels (children of root — stay on main window)
        self.output = OutputPanel(root)
        self.output.setFixedSize(390, 440)

        self.chat = ChatPanel(root)
        self.chat.setFixedSize(510, 390)
        self.chat.mic_btn.clicked.connect(self._toggle_voice)
        self.chat.command_entered.connect(self.process_command)

        # V12: ball is a STANDALONE top-level window, NOT a child of root
        self.ball = AssistantBall()
        self.ball.clicked.connect(self._on_ball_clicked)

        self._place_panels()

        self.content.raise_()
        self.chat.raise_()
        self.output.raise_()
        # ball is not a child, so no raise_ needed here

    def _place_panels(self):
        W, H = self.width(), self.height()
        mid_y = (H - 390) // 2 + 10
        if hasattr(self, "chat"):
            self.chat.move(W - 510 - 20, mid_y)
        if hasattr(self, "output"):
            self.output.move(20, (H - 440) // 2 + 10)

    def _setup_shortcuts(self):
        # ESC: toggle ball-only mode (no black screen)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._toggle_hidden)
        # SPACE: toggle listening on/off
        QShortcut(QKeySequence("Space"),  self).activated.connect(self._toggle_voice)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self._show_chat)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._hide_panels)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self._quit)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._quick_screenshot)
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self._show_settings)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._show_output)

    def _setup_tray(self):
        px = QPixmap(48, 48)
        px.fill(QColor(0, 0, 0, 0))
        pr = QPainter(px)
        pr.setRenderHint(QPainter.RenderHint.Antialiasing)
        pr.setPen(QPen(C_CYAN, 2.5))
        pr.drawEllipse(5, 5, 38, 38)
        f = QFont("Segoe UI", 13, QFont.Weight.Bold)
        pr.setFont(f)
        pr.setPen(QPen(C_CYAN))
        pr.drawText(QRect(0, 0, 48, 48), Qt.AlignmentFlag.AlignCenter, "J")
        pr.end()

        self.tray = QSystemTrayIcon(QIcon(px), self)
        m = QMenu()
        m.addAction("Show JARVIS",  self._show_all)
        m.addAction("Chat",         self._show_chat)
        m.addAction("Output",       self._show_output)
        m.addSeparator()
        m.addAction("Settings",     self._show_settings)
        m.addSeparator()
        m.addAction("Quit",         self._quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda r: self._show_all()
            if r == QSystemTrayIcon.ActivationReason.DoubleClick
            else None)
        self.tray.show()

    # ── Module init ────────────────────────────────────────────────────────
    def _init_modules(self):
        def _load():
            try:
                from core.brain import JarvisBrain
                self.brain = JarvisBrain(self.settings)
                self.status_signal.emit("BRAIN READY", "success")
                self.chat.add_message(
                    "JARVIS V12 hazir hai, Sir! Multi-model Ollama + Chrome research ready.", "JARVIS")
            except Exception as e:
                self.status_signal.emit("BRAIN ERR", "error")
                print(f"[WIN] brain error: {e}")

            try:
                from speech.tts_engine import TTSEngine
                self.speaker = TTSEngine(self.settings)
                print("[WIN] TTS loaded")
            except Exception as e:
                print(f"[WIN] TTS error: {e}")

            try:
                from speech.stt_engine import STTEngine
                self.listener = STTEngine(self.settings)
                print("[WIN] STT loaded")
            except Exception as e:
                print(f"[WIN] STT error: {e}")
                self.status_signal.emit("STT ERROR", "error")

            try:
                from tools.automation import Automation
                self.automation = Automation(self.settings)
                if self.brain:
                    self.brain.automation = self.automation
                    self.automation._brain = self.brain  # V12: two-way link
                print("[WIN] Automation loaded")
            except Exception as e:
                print(f"[WIN] automation error: {e}")

            self.status_signal.emit("READY", "normal")

        threading.Thread(target=_load, daemon=True, name="module-init").start()

    # ── V12: ESC → Ball only (NO black screen) ────────────────────────────
    def _toggle_hidden(self):
        if self._hidden:
            self._show_all()
        else:
            self._hide_to_ball()

    def _hide_to_ball(self):
        """
        Hide the full JARVIS interface. Show ONLY the small ball.
        The main window is hidden entirely — no black screen remains.
        """
        self._hidden = True
        self.chat.hide_panel()
        self.output.hide_panel()
        # Hide the full main window — this removes the starfield + content
        self.hide()
        # Show the standalone ball widget
        self.ball.set_state("idle")
        self.ball.show_ball()

    def _show_all(self):
        self._hidden = False
        self.ball.hide_ball()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_ball_clicked(self):
        """Ball click → restore full interface."""
        self._show_all()

    def _show_chat(self):
        if self._hidden:
            self._show_all()
        self.chat.show_panel()

    def _show_output(self):
        if self._hidden:
            self._show_all()
        self.output.show_panel()

    def _hide_panels(self):
        self.chat.hide_panel()
        self.output.hide_panel()

    def _show_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_settings = dlg.get_settings()
            self._hinglish_mode       = new_settings["hinglish_display_mode"]
            self._tts_enabled         = new_settings["tts_enabled"]
            self._vision_enabled      = new_settings["vision_enabled"]
            self._web_search_enabled  = new_settings["web_search_enabled"]
            self._chrome_research     = new_settings["chrome_research_enabled"]
            self.settings["hinglish_display_mode"] = self._hinglish_mode
            if self.brain:
                self.brain.vision_enabled         = self._vision_enabled
                self.brain.web_search_enabled     = self._web_search_enabled
                self.brain.chrome_research_enabled = self._chrome_research
            self.chat.add_message(
                f"Settings updated: TTS={'ON' if self._tts_enabled else 'OFF'} | "
                f"Chrome={'ON' if self._chrome_research else 'OFF'}", "SYSTEM")

    # ── V12: SPACE = toggle listening (ON/OFF) ─────────────────────────────
    def _toggle_voice(self):
        if self._listening:
            # Second SPACE press → stop listening
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        if self._busy:
            return
        if not self.listener:
            self.statusbar.set("STT NOT AVAILABLE", "error")
            self.chat.add_message("Speech recognition not available.", "SYSTEM")
            return

        self._listening = True
        self._show_chat()

        # Ball glow: ORANGE while listening
        self.ball.set_state("listening")
        self.reactor.set_mode("listening")
        self.statusbar.set("🎙️ LISTENING… (SPACE to stop)", "warning")
        self.chat.add_listening()
        self.chat.mic_btn.setText("🔴 STOP")
        self.chat.mic_btn.setStyleSheet(
            "background:rgba(255,60,60,160);color:#fff;border-radius:8px;"
            "font-weight:bold;")

        self._listen = ListenWorker(self.listener)
        self._listen.recognised.connect(self.stt_heard_signal.emit)
        self._listen.failed.connect(self.stt_fail_signal.emit)
        self._listen.start()

    def _stop_listening(self):
        self._listening = False
        if self._listen and self._listen.isRunning():
            try:
                if self.listener:
                    self.listener.stop_listening()
            except Exception:
                pass
        self._reset_mic_btn()
        self.ball.set_state("idle")
        self.reactor.set_mode("idle")
        self.statusbar.set("READY")
        self.chat.add_message("Listening stopped.", "SYSTEM")

    def _reset_mic_btn(self):
        self._listening = False
        self.chat.mic_btn.setText("🎤")
        self.chat.mic_btn.setStyleSheet("")

    def _on_stt_heard(self, text: str):
        self._listening = False
        self._reset_mic_btn()

        # Ball glow: GREEN while working
        self.ball.set_state("thinking")
        self.reactor.set_mode("thinking")
        self.statusbar.set("PROCESSING…", "warning")
        self._show_chat()
        self.chat.add_message(text, "USER")
        self.process_command(text)

    def _on_stt_fail(self):
        self._listening = False
        self._reset_mic_btn()
        self.ball.set_state("idle")
        self.reactor.set_mode("idle")
        self.statusbar.set("READY")
        self.chat.add_message(
            "Kuch suna nahi — dobara SPACE dabayein", "SYSTEM")

    # ── Command processing ─────────────────────────────────────────────────
    def process_command(self, text: str):
        if not self.brain:
            self.chat.add_message("Brain still loading, Sir. Please wait.", "JARVIS")
            return
        if self._busy:
            return

        self._busy = True
        # Ball glow: GREEN while working
        self.ball.set_state("thinking")
        self.reactor.set_mode("thinking")
        self.statusbar.set("THINKING…", "warning")
        self._show_chat()
        self.chat.add_thinking()

        hint = "chat"
        tl = text.lower()
        if any(w in tl for w in ["screen", "read screen", "dekho", "kya hai screen pe"]):
            hint = "screen"
        elif any(w in tl for w in ["search", "find", "google", "news", "latest",
                                    "who is", "what is", "batao", "research"]):
            hint = "search"
        elif any(w in tl for w in ["code", "python", "script", "function", "write code"]):
            hint = "code"
        elif any(w in tl for w in ["write", "essay", "story", "poem", "creative"]):
            hint = "creative"

        self._worker = BrainWorker(self.brain, text, hint)
        self._worker.result_ready.connect(self.ai_reply_signal.emit)
        self._worker.error_occurred.connect(self.ai_error_signal.emit)
        self._worker.finished.connect(self._on_brain_done)
        self._worker.start()

    def _on_brain_done(self):
        self._busy = False

    def _on_actions_done(self):
        """Called on main thread when all action chain steps complete."""
        self.ball.set_state("done")
        self.statusbar.set("DONE ✓", "success")
        self.reactor.set_mode("idle")
        # Show any pending screenshot
        if hasattr(self, "_pending_screenshot") and self._pending_screenshot:
            self.show_output_image(self._pending_screenshot, "Screenshot")
            self._pending_screenshot = None
        # Reset to idle after 3s
        QTimer.singleShot(3000, lambda: (
            self.ball.set_state("idle") or
            self.statusbar.set("READY")
        ))

    def _on_ai_reply(self, response: str, actions: list):
        # Remove "Processing…" line
        cur = self.chat.display.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.select(QTextCursor.SelectionType.LineUnderCursor)
        if "Processing…" in cur.selectedText():
            cur.removeSelectedText()
            cur.deletePreviousChar()

        try:
            from core.brain import hindi_to_hinglish
            disp = hindi_to_hinglish(response) if self._hinglish_mode else response
        except Exception:
            disp = response

        self.chat.add_message(disp, "JARVIS")

        # V12: AI always speaks (voice response to voice input)
        if self._tts_enabled and self.speaker:
            self.speak_signal.emit(response)

        # Execute action chain in background thread (no GUI freeze)
        if self.automation and actions:
            self.output.show_panel()
            self.output.add_cmd(f"⚙️ {len(actions)} action(s) executing…", True)

            def _run_actions():
                for i, act in enumerate(actions):
                    try:
                        ok, msg  = self.automation.execute(act)
                        a_name   = act.get("action", "?")
                        # Use SIGNALS not QTimer — thread-safe, no QBasicTimer warnings
                        self.status_signal.emit(f"ACTION {i+1}/{len(actions)}", "warning")
                        self.action_chat_signal.emit(msg, "ACTION_OK" if ok else "ACTION_FAIL")
                        self.action_cmd_signal.emit(f"{a_name} → {msg}", ok)

                        # Screenshot display (done on main thread via signal)
                        if a_name == "screenshot" and ok:
                            shots_dir = BASE / "data" / "screenshots"
                            if shots_dir.exists():
                                files = sorted(shots_dir.glob("*.png"))
                                if files:
                                    # show_output_image must run on main thread
                                    # Use a lambda via status_signal as proxy trigger
                                    self._pending_screenshot = str(files[-1])

                    except Exception as e:
                        self.action_chat_signal.emit(f"Action failed: {e}", "ACTION_FAIL")
                        self.action_cmd_signal.emit(f"Error: {e}", False)

                # Signal completion — runs _on_actions_done on main thread
                self.action_done_signal.emit()

            threading.Thread(target=_run_actions, daemon=True, name="action-chain").start()
        else:
            # No actions — just set done state
            self.ball.set_state("done")
            self.statusbar.set("READY")
            self.reactor.set_mode("idle")
            QTimer.singleShot(3000, lambda: self.ball.set_state("idle"))

    def _on_ai_error(self, err: str):
        self.chat.add_message(f"Error: {err}", "SYSTEM")
        self.statusbar.set("ERROR", "error")
        self.ball.set_state("idle")
        self.reactor.set_mode("idle")
        self._busy = False

    def _on_speak(self, text: str):
        # Ball glow: GREEN while speaking
        self.ball.set_state("speaking")
        self.reactor.set_mode("speaking")
        self.statusbar.set("SPEAKING", "success")
        if self.speaker:
            def _do_speak():
                try:
                    self.speaker.speak(text)
                except Exception as e:
                    print(f"[TTS] Speak error: {e}")
                finally:
                    self.status_signal.emit("READY", "normal")
                    # Ball back to BLUE (done) after speaking
                    self.ball.set_state("done")
                    QTimer.singleShot(2000, lambda: self.ball.set_state("idle"))
            threading.Thread(target=_do_speak, daemon=True).start()
        else:
            QTimer.singleShot(2500, lambda: self.statusbar.set("READY"))
            QTimer.singleShot(3200, lambda: self.reactor.set_mode("idle"))

    # ── Output helpers ──────────────────────────────────────────────────────
    def show_output_image(self, path_or_pixmap, caption: str = ""):
        if self._hidden:
            self._show_all()
        self.output.add_image(path_or_pixmap, caption)

    def show_output_text(self, text: str, tab: str = "INFO"):
        if self._hidden:
            self._show_all()
        self.output.add_text(text, tab)

    def _quick_screenshot(self):
        if self.automation:
            ok, msg = self.automation.execute({"action": "screenshot", "target": ""})
            self.chat.add_message(msg, "JARVIS" if ok else "SYSTEM")
            if ok:
                shots_dir = BASE / "data" / "screenshots"
                if shots_dir.exists():
                    files = sorted(shots_dir.glob("*.png"))
                    if files:
                        self.show_output_image(str(files[-1]), "Quick Screenshot")

    # ── Resize / drag / quit ───────────────────────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        cw = self.centralWidget()
        if cw:
            cw.setGeometry(self.rect())
        for w in (self.starfield, self.content):
            if w:
                w.setGeometry(self.rect())
        self._place_panels()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if (e.buttons() == Qt.MouseButton.LeftButton
                and hasattr(self, "_drag_pos")):
            self.move(self.pos() +
                      e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def closeEvent(self, e):
        e.ignore()
        self._hide_to_ball()

    def _quit(self):
        self.tray.hide()
        self.ball.hide_ball()
        if self.speaker:
            try:
                self.speaker.stop()
            except Exception:
                pass
        QApplication.instance().quit()
