
"""SQLite persistence for RoastBhai users, sessions, and conversations."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "ROASTBHAI_DB_PATH",
        Path(__file__).with_name("roastbhai.sqlite3"),
    )
)


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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL DEFAULT '',
            password_hash TEXT,
            google_sub TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL
                REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Safe migration for existing conversations.
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(conversations)")
        }

        if "user_id" not in columns:
            db.execute("""
                ALTER TABLE conversations
                ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            """)

        db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id);

        CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_conversations_user
            ON conversations(user_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON sessions(user_id);

        CREATE INDEX IF NOT EXISTS idx_sessions_expiry
            ON sessions(expires_at);
        """)


# -------------------------
# User accounts
# -------------------------

def create_user(email: str, name: str, password_hash: str) -> int:
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO users(email, name, password_hash) VALUES (?, ?, ?)",
            (email.strip().lower(), name.strip(), password_hash),
        )
        return cursor.lastrowid


def get_user_by_email(email: str):
    with connection() as db:
        row = db.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int):
    with connection() as db:
        row = db.execute(
            "SELECT id, email, name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_or_create_google_user(
    google_sub: str,
    email: str,
    name: str,
) -> int:
    email = email.strip().lower()
    name = name.strip()

    with connection() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE google_sub = ?",
            (google_sub,),
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE users SET email = ?, name = ? WHERE id = ?",
                (email, name, existing["id"]),
            )
            return existing["id"]

        # Link Google to an existing account only when Google
        # has already verified the email in the OAuth callback.
        existing_email = db.execute(
            "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()

        if existing_email:
            db.execute(
                "UPDATE users SET google_sub = ?, name = ? WHERE id = ?",
                (google_sub, name, existing_email["id"]),
            )
            return existing_email["id"]

        cursor = db.execute(
            """
            INSERT INTO users(email, name, google_sub)
            VALUES (?, ?, ?)
            """,
            (email, name, google_sub),
        )
        return cursor.lastrowid


# -------------------------
# Login sessions
# -------------------------

def create_session(
    user_id: int,
    token_hash: str,
    expires_at: str,
):
    with connection() as db:
        db.execute(
            """
            INSERT INTO sessions(user_id, token_hash, expires_at)
            VALUES (?, ?, ?)
            """,
            (user_id, token_hash, expires_at),
        )


def get_session_user(token_hash: str):
    with connection() as db:
        row = db.execute(
            """
            SELECT u.id, u.email, u.name
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.expires_at > datetime('now')
            """,
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None


def delete_session(token_hash: str):
    with connection() as db:
        db.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (token_hash,),
        )


def delete_expired_sessions():
    with connection() as db:
        db.execute(
            "DELETE FROM sessions WHERE expires_at <= datetime('now')"
        )


# -------------------------
# Conversations
# -------------------------

def create_conversation(user_id: int, title: str) -> int:
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO conversations(user_id, title) VALUES (?, ?)",
            (user_id, title),
        )
        return cursor.lastrowid


def get_conversation(conversation_id: int, user_id: int):
    with connection() as db:
        convo = db.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()

        if not convo:
            return None

        messages = db.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()

        return {
            **dict(convo),
            "messages": [dict(row) for row in messages],
        }


def list_conversations(user_id: int):
    with connection() as db:
        rows = db.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                (
                    SELECT content
                    FROM messages
                    WHERE conversation_id = c.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS preview
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (user_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def add_message(
    conversation_id: int,
    user_id: int,
    role: str,
    content: str,
):
    with connection() as db:
        owned = db.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()

        if not owned:
            return False

        db.execute(
            """
            INSERT INTO messages(conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, content),
        )

        db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )

        return True


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with connection() as db:
        return db.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).rowcount > 0


def delete_all_conversations(user_id: int):
    with connection() as db:
        db.execute(
            "DELETE FROM conversations WHERE user_id = ?",
            (user_id,),
        )
