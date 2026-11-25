"""SQLite persistence for RoastBhai conversations."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("ROASTBHAI_DB_PATH", Path(__file__).with_name("roastbhai.sqlite3")))

@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
        """)

def create_conversation(title: str) -> int:
    with connection() as db:
        cursor = db.execute("INSERT INTO conversations(title) VALUES (?)", (title,))
        return cursor.lastrowid

def get_conversation(conversation_id: int):
    with connection() as db:
        convo = db.execute("SELECT id,title,created_at,updated_at FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not convo: return None
        messages = db.execute("SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
        return {**dict(convo), "messages": [dict(row) for row in messages]}

def list_conversations():
    with connection() as db:
        return [dict(row) for row in db.execute("""SELECT c.id,c.title,c.created_at,c.updated_at,
            (SELECT content FROM messages WHERE conversation_id=c.id ORDER BY id DESC LIMIT 1) AS preview
            FROM conversations c ORDER BY c.updated_at DESC,c.id DESC""")]

def add_message(conversation_id: int, role: str, content: str):
    with connection() as db:
        db.execute("INSERT INTO messages(conversation_id,role,content) VALUES (?,?,?)", (conversation_id,role,content))
        db.execute("UPDATE conversations SET updated_at=datetime('now') WHERE id=?", (conversation_id,))

def delete_conversation(conversation_id: int) -> bool:
    with connection() as db:
        return db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,)).rowcount > 0

def delete_all_conversations():
    with connection() as db: db.execute("DELETE FROM conversations")
