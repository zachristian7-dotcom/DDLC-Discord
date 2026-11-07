import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "ddlc_memory.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character TEXT NOT NULL,
                speaker TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT ''
            )
        """)

        # Upgrade databases created by earlier versions without losing data.
        for table in ("messages", "memories"):
            columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if "user_id" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
                )

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_character_user
            ON messages(character, user_id, id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_character_user
            ON memories(character, user_id, id)
        """)


def save_message(character, speaker, content, user_id):
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages
            (character, speaker, content, timestamp, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (character.lower(), speaker, content, timestamp, str(user_id))
        )


def get_recent_messages(character, user_id, limit=20):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT speaker, content, timestamp
            FROM messages
            WHERE character = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (character.lower(), str(user_id), limit)
        ).fetchall()
    return list(reversed(rows))


def save_memory(character, user_id, category, content):
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO memories
            (character, category, content, timestamp, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (character.lower(), category, content, timestamp, str(user_id))
        )
        return cursor.lastrowid


def get_memories(character, user_id, limit=50):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, category, content, timestamp
            FROM memories
            WHERE character = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (character.lower(), str(user_id), limit)
        ).fetchall()
    return rows


def delete_memory(memory_id, user_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            (memory_id, str(user_id))
        )
        return cursor.rowcount > 0


if __name__ == "__main__":
    initialize_database()
    print("Literature Club memory database initialized!")
