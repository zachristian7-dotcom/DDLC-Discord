import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "ddlc_memory.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)


def get_connection():
    if USE_POSTGRES:
        import psycopg
        # Supabase transaction poolers may not support server-side prepared statements.
        return psycopg.connect(
            DATABASE_URL,
            sslmode="require",
            prepare_threshold=None,
        )

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _sql(statement):
    """Use the placeholder style required by the selected database."""
    return statement.replace("?", "%s") if USE_POSTGRES else statement


def initialize_database():
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    character TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id BIGSERIAL PRIMARY KEY,
                    character TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS club_events (
                    event_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_club_events_channel
                ON club_events(channel_id, timestamp)
            """)
            for table in ("messages", "memories"):
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    "user_id TEXT NOT NULL DEFAULT ''"
                )
        else:
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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS club_events (
                    event_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_club_events_channel
                ON club_events(channel_id, timestamp)
            """)

            # Upgrade older local databases without losing existing data.
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
            _sql("""
                INSERT INTO messages
                (character, speaker, content, timestamp, user_id)
                VALUES (?, ?, ?, ?, ?)
            """),
            (character.lower(), speaker, content, timestamp, str(user_id))
        )


def get_recent_messages(character, user_id, limit=20):
    with get_connection() as conn:
        rows = conn.execute(
            _sql("""
                SELECT speaker, content, timestamp
                FROM messages
                WHERE character = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """),
            (character.lower(), str(user_id), limit)
        ).fetchall()
    return list(reversed(rows))



def get_recent_user_messages(user_id, limit=20):
    """Return distinct recent user-authored messages across character conversations."""
    with get_connection() as conn:
        rows = conn.execute(
            _sql("""
                SELECT content, MAX(timestamp) AS latest
                FROM messages
                WHERE user_id = ?
                  AND LOWER(speaker) NOT IN ('sayori', 'natsuki', 'yuri', 'monika')
                GROUP BY content
                ORDER BY latest DESC
                LIMIT ?
            """),
            (str(user_id), int(limit))
        ).fetchall()
    return [row[0] for row in reversed(rows)]


def save_club_event(event_id, channel_id, speaker, content):
    """Save one channel-visible event once, even though all four bots see it."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            _sql("""
                INSERT INTO club_events
                (event_id, channel_id, speaker, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
            """),
            (str(event_id), str(channel_id), str(speaker), str(content), timestamp)
        )


def get_recent_club_events(channel_id, limit=16):
    """Return shared, channel-visible conversation context in chronological order."""
    with get_connection() as conn:
        rows = conn.execute(
            _sql("""
                SELECT speaker, content, timestamp
                FROM club_events
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """),
            (str(channel_id), int(limit))
        ).fetchall()
    return list(reversed(rows))


def save_memory(character, user_id, category, content):
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            _sql("""
                INSERT INTO memories
                (character, category, content, timestamp, user_id)
                VALUES (?, ?, ?, ?, ?)
            """),
            (character.lower(), category, content, timestamp, str(user_id))
        )
        if USE_POSTGRES:
            # Fetch the generated ID from PostgreSQL.
            row = conn.execute("SELECT currval(pg_get_serial_sequence('memories', 'id'))").fetchone()
            return row[0]
        return cursor.lastrowid


def get_memories(character, user_id, limit=50):
    with get_connection() as conn:
        rows = conn.execute(
            _sql("""
                SELECT id, category, content, timestamp
                FROM memories
                WHERE character = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """),
            (character.lower(), str(user_id), limit)
        ).fetchall()
    return rows


def delete_memory(character, memory_id, user_id):
    with get_connection() as conn:
        cursor = conn.execute(
            _sql("DELETE FROM memories WHERE character = ? AND id = ? AND user_id = ?"),
            (character.lower(), memory_id, str(user_id))
        )
        return cursor.rowcount > 0


if __name__ == "__main__":
    initialize_database()
    backend = "Supabase PostgreSQL" if USE_POSTGRES else "local SQLite"
    print(f"Literature Club memory database initialized ({backend})!")
