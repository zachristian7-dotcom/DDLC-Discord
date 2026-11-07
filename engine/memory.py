
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
                timestamp TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_character
            ON messages(character, id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_character
            ON memories(character, id)
        """)


def save_message(character, speaker, content):
    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages
            (character, speaker, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (character.lower(), speaker, content, timestamp)
        )


def get_recent_messages(character, limit=20):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT speaker, content, timestamp
            FROM messages
            WHERE character = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (character.lower(), limit)
        ).fetchall()

    return list(reversed(rows))


def save_memory(character, category, content):
    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO memories
            (character, category, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (character.lower(), category, content, timestamp)
        )


def get_memories(character, limit=50):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, content, timestamp
            FROM memories
            WHERE character = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (character.lower(), limit)
        ).fetchall()

    return rows


def delete_memory(memory_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,)
        )


if __name__ == "__main__":
    initialize_database()
    print("Literature Club memory database initialized!")
