"""
learning/trainer.py — JARVIS OMEGA V12

Persistent learning system:
- Saves every task + its steps to SQLite
- Stores app UI knowledge (where buttons are, what shortcuts work)
- Saves web research results with TTL
- Saves programming language snippets
- Builds a growing personal knowledge base
"""
from __future__ import annotations
import json, sqlite3, threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

BASE = Path(__file__).resolve().parent.parent


class JarvisTrainer:
    def __init__(self, settings: dict):
        self.settings = settings
        db_path = BASE / "data" / "knowledge" / "jarvis_knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn  = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_info (
                    app_name TEXT PRIMARY KEY, exe_path TEXT, ui_notes TEXT,
                    shortcuts TEXT, last_used TEXT, is_installed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS task_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, result TEXT,
                    app_used TEXT, steps TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS web_research (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, summary TEXT,
                    source TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_msg TEXT, ai_msg TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS context_state (
                    key TEXT PRIMARY KEY, value TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS code_snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, topic TEXT,
                    code TEXT, description TEXT, ts TEXT);
                CREATE TABLE IF NOT EXISTS ui_elements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, app_name TEXT,
                    element_text TEXT, x INTEGER, y INTEGER, action TEXT, ts TEXT);
            """)
            self.conn.commit()

    def learn_app_ui(self, app_name: str, element_text: str, x: int, y: int, action: str = "click"):
        with self._lock:
            self.conn.execute(
                "INSERT INTO ui_elements(app_name,element_text,x,y,action,ts) VALUES(?,?,?,?,?,?)",
                (app_name.lower(), element_text, x, y, action, datetime.now().isoformat()))
            self.conn.commit()

    def recall_app_ui(self, app_name: str, element_hint: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT element_text,x,y,action FROM ui_elements WHERE app_name=? AND element_text LIKE ? ORDER BY id DESC LIMIT 1",
            (app_name.lower(), f"%{element_hint}%")).fetchone()
        return {"text": row[0], "x": row[1], "y": row[2], "action": row[3]} if row else None

    def learn_app_shortcut(self, app_name: str, action: str, shortcut: str):
        existing = self.conn.execute("SELECT shortcuts FROM app_info WHERE app_name=?", (app_name.lower(),)).fetchone()
        if existing:
            current = json.loads(existing[0] or "{}")
            current[action] = shortcut
            with self._lock:
                self.conn.execute("UPDATE app_info SET shortcuts=? WHERE app_name=?",
                                  (json.dumps(current), app_name.lower()))
                self.conn.commit()
        else:
            with self._lock:
                self.conn.execute("INSERT INTO app_info(app_name,shortcuts,last_used) VALUES(?,?,?)",
                                  (app_name.lower(), json.dumps({action: shortcut}), datetime.now().isoformat()))
                self.conn.commit()

    def get_app_shortcuts(self, app_name: str) -> Dict[str, str]:
        row = self.conn.execute("SELECT shortcuts FROM app_info WHERE app_name=?", (app_name.lower(),)).fetchone()
        if row and row[0]:
            try: return json.loads(row[0])
            except: pass
        return {}

    def save_code(self, language: str, topic: str, code: str, description: str = ""):
        with self._lock:
            self.conn.execute("INSERT INTO code_snippets(language,topic,code,description,ts) VALUES(?,?,?,?,?)",
                              (language, topic, code, description, datetime.now().isoformat()))
            self.conn.commit()

    def recall_code(self, language: str = "", topic: str = "") -> List[Dict]:
        if language and topic:
            rows = self.conn.execute("SELECT language,topic,code,description FROM code_snippets WHERE language=? AND topic LIKE ? ORDER BY id DESC LIMIT 5", (language, f"%{topic}%")).fetchall()
        elif language:
            rows = self.conn.execute("SELECT language,topic,code,description FROM code_snippets WHERE language=? ORDER BY id DESC LIMIT 5", (language,)).fetchall()
        else:
            rows = self.conn.execute("SELECT language,topic,code,description FROM code_snippets ORDER BY id DESC LIMIT 5").fetchall()
        return [{"lang": r[0], "topic": r[1], "code": r[2], "desc": r[3]} for r in rows]

    def get_stats(self) -> Dict[str, int]:
        stats = {}
        for t in ["task_memory","web_research","conversations","ui_elements","code_snippets"]:
            try: stats[t] = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except: stats[t] = 0
        return stats

    def export_knowledge(self, path: str = "") -> str:
        if not path:
            path = str(BASE / "data" / "knowledge" / f"export_{datetime.now():%Y%m%d_%H%M%S}.json")
        data = {
            "apps":     [dict(zip(["name","exe","ui","shortcuts","used","installed"], r)) for r in self.conn.execute("SELECT * FROM app_info").fetchall()],
            "tasks":    [dict(zip(["id","task","result","app","steps","ts"], r)) for r in self.conn.execute("SELECT * FROM task_memory ORDER BY id DESC LIMIT 200").fetchall()],
            "research": [dict(zip(["id","query","summary","source","ts"], r)) for r in self.conn.execute("SELECT * FROM web_research ORDER BY id DESC LIMIT 200").fetchall()],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def close(self):
        try: self.conn.close()
        except: pass
