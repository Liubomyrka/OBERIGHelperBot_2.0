import sqlite3
import os
import json
import re
from utils.logger import logger
from utils.privacy import mask_user_id
from utils.db_crypto import decrypt_text, encrypt_text, is_encrypted
from config import DB_ENCRYPTION_KEY
from typing import Optional
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
_conn = None

_ENCRYPTED_KEY_PREFIXES = ("oberig_chat_history_",)
_ENCRYPTED_KEY_EXACT = {"feedback_history", "bot_users_info", "group_chats"}


def _is_sensitive_key(key: str) -> bool:
    if key in _ENCRYPTED_KEY_EXACT:
        return True
    return key.startswith(_ENCRYPTED_KEY_PREFIXES)


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        try:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            logger.info(f"🔗 Підключення до бази даних: {DB_PATH}")
        except sqlite3.Error as e:
            logger.error(f"❌ Помилка підключення до бази даних: {e}")
            raise
    return _conn


@contextmanager
def get_cursor():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"❌ Помилка при виконанні запиту: {e}")
        raise
    finally:
        cursor.close()


def create_tables():
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS persistent_reminders (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_notifications (
                    video_id TEXT PRIMARY KEY,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_type TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_reminder_hashes (
                    event_id TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    PRIMARY KEY (event_id, reminder_type)
                )
            """)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_message_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    message_date TEXT NOT NULL,
                    text TEXT NOT NULL,
                    is_reply INTEGER DEFAULT 0,
                    reply_to_user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, message_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gmi_chat_date ON group_message_index(chat_id, message_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gmi_user_date ON group_message_index(user_id, message_date)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_message_embeddings (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    embedding TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    fact_type TEXT NOT NULL,
                    event_name TEXT,
                    event_date TEXT,
                    event_time TEXT,
                    location TEXT,
                    responsible TEXT,
                    deadline TEXT,
                    details TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gf_chat_type_date ON group_facts(chat_id, fact_type, event_date)"
            )
            connection.commit()
            logger.info("✅ Таблиці бази даних створені успішно.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при створенні таблиць: {e}")
def init_db():
    try:
        create_tables()
        default_values = {
            "bot_users": ["611511159"],
            "users_with_reminders": ["611511159", "1564008807"],
            "video_notifications_disabled": {},
            "group_notifications_disabled": {},
            "group_chats": [],
            "sent_reminders": {"2025-02-14": []},
            "daily_reminder_sent": False,
            "hourly_reminder_sent": False,
            "last_known_video": "k0q5Q7Z32PQ",
            "commands_stats": {},
            "users_activity": {},
            "sent_reminders_persistent": {},
            "persistent_reminders": {},
            "sent_videos": [],
            "bot_users_info": {"611511159": "Liubomyr"},
            "last_video_check": None
        }
        for key, default_value in default_values.items():
            current_value = get_value(key)
            if current_value is None:
                set_value(
                    key,
                    json.dumps(default_value) if isinstance(default_value, (list, dict)) else str(default_value)
                )
                logger.info(f"✅ Ініціалізовано значення за замовчуванням для {key}")
        logger.info("✅ База даних ініціалізована коректно.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при ініціалізації бази даних: {e}")


def migrate_database():
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            tables = ["users", "groups", "reminders", "persistent_reminders"]
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table});")
                columns = [column[1] for column in cursor.fetchall()]
                if "created_at" not in columns or "updated_at" not in columns:
                    try:
                        logger.info(f"🔄 Початок міграції таблиці {table}")
                        cursor.execute("PRAGMA foreign_keys=OFF;")
                        cursor.execute(f"DROP TABLE IF EXISTS {table}_backup;")
                        cursor.execute(f"CREATE TEMPORARY TABLE {table}_backup AS SELECT * FROM {table};")
                        cursor.execute(f"DROP TABLE {table};")
                        cursor.execute(f"""
                            CREATE TABLE {table} (
                                key TEXT PRIMARY KEY,
                                value TEXT,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                        cursor.execute(f"""
                            INSERT INTO {table} (key, value, created_at, updated_at)
                            SELECT key, value, COALESCE(created_at, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP
                            FROM {table}_backup;
                        """)
                        cursor.execute(f"DROP TABLE {table}_backup;")
                        cursor.execute("PRAGMA foreign_keys=ON;")
                        logger.info(f"✅ Успішно оновлено структуру таблиці {table}")
                    except sqlite3.Error as e:
                        logger.error(f"❌ Помилка при міграції таблиці {table}: {e}")

            # Додаємо колонку, якщо її ще немає
            cursor.execute("PRAGMA table_info(sent_notifications);")
            columns = [col[1] for col in cursor.fetchall()]
            if "message_id" not in columns:
                cursor.execute("ALTER TABLE sent_notifications ADD COLUMN message_id TEXT;")
                logger.info("✅ Додано колонку message_id до sent_notifications")

            # 🔧 Створюємо або оновлюємо таблицю birthday_greetings
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS birthday_greetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    date_sent TEXT NOT NULL,
                    greeting_type TEXT NOT NULL CHECK(greeting_type IN ('morning', 'evening')),
                    greeting_text TEXT,
                    UNIQUE(event_id, date_sent, greeting_type)
                )
                """
            )
            cursor.execute("PRAGMA table_info(birthday_greetings);")
            columns = [col[1] for col in cursor.fetchall()]
            if "greeting_text" not in columns:
                cursor.execute("ALTER TABLE birthday_greetings ADD COLUMN greeting_text TEXT")
                logger.info("✅ Додано колонку greeting_text до birthday_greetings")
            # Забезпечуємо наявність унікального індексу відправлених привітань
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_birthday_unique ON birthday_greetings (event_id, date_sent, greeting_type)"
            )

            # 🔧 Створюємо таблицю event_reminder_hashes, якщо вона ще не існує
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_reminder_hashes (
                    event_id TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    PRIMARY KEY (event_id, reminder_type)
                )
            """)
            logger.info("✅ Таблиця event_reminder_hashes створена або вже існує.")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_message_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    message_date TEXT NOT NULL,
                    text TEXT NOT NULL,
                    is_reply INTEGER DEFAULT 0,
                    reply_to_user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, message_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gmi_chat_date ON group_message_index(chat_id, message_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gmi_user_date ON group_message_index(user_id, message_date)"
            )
            logger.info("✅ Таблиця group_message_index створена або вже існує.")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_message_embeddings (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    embedding TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS group_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    fact_type TEXT NOT NULL,
                    event_name TEXT,
                    event_date TEXT,
                    event_time TEXT,
                    location TEXT,
                    responsible TEXT,
                    deadline TEXT,
                    details TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gf_chat_type_date ON group_facts(chat_id, fact_type, event_date)"
            )
            logger.info("✅ Таблиці group_message_embeddings та group_facts створені або вже існують.")

            connection.commit()
            logger.info("🎉 Міграцію бази даних завершено успішно")
    except sqlite3.Error as e:
        logger.error(f"❌ Критична помилка міграції бази даних: {e}")


def set_value(key: str, value: str, table: str = "users"):
    try:
        with get_cursor() as cursor:
            if "group" in key.lower():
                table = "groups"
            elif "reminder" in key.lower() or "persistent" in key.lower():
                table = "persistent_reminders"
            stored_value = encrypt_text(value, DB_ENCRYPTION_KEY) if _is_sensitive_key(key) else value
            cursor.execute(f"""
                INSERT OR REPLACE INTO {table} (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (key, stored_value))
        logger.info(f"✅ Збережено значення для ключа {key} в таблиці {table}")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні значення для ключа {key}: {e}")


def get_value(key: str) -> Optional[str]:
    try:
        with get_cursor() as cursor:
            table = "reminders"
            if key.startswith(
                (
                    "bot_users",
                    "video_notifications_disabled",
                    "users_",
                    "last_video_check",
                    "calendar_events_cache",
                    "yt_",
                    "last_known_video",
                )
            ):
                table = "users"
            elif key.startswith(("group_chats", "group_notifications_disabled")):
                table = "groups"
            elif key.startswith(("sent_reminders_persistent", "persistent_", "sent_videos", "users_with_reminders")) or "reminder" in key.lower() or "persistent" in key.lower():
                table = "persistent_reminders"
            cursor.execute(f"SELECT value FROM {table} WHERE key=?", (key,))
            result = cursor.fetchone()
            if not result:
                return None
            raw_value = result[0]
            if _is_sensitive_key(key):
                return decrypt_text(raw_value, DB_ENCRYPTION_KEY)
            return raw_value
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при отриманні значення для ключа '{key}': {e}")
        return None


def delete_value(key: str):
    try:
        with get_cursor() as cursor:
            table = "reminders"
            if key.startswith(("bot_users", "video_notifications_disabled")):
                table = "users"
            elif key.startswith(("group_chats", "group_notifications_disabled")):
                table = "groups"
            elif key.startswith(("sent_reminders_persistent", "persistent_")) or "reminder" in key.lower() or "persistent" in key.lower():
                table = "persistent_reminders"
            cursor.execute(f"DELETE FROM {table} WHERE key=?", (key,))
        logger.info(f"✅ Видалено значення для ключа '{key}'.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при видаленні значення для ключа '{key}': {e}")


def get_event_reminder_hash(event_id: str, reminder_type: str) -> Optional[str]:
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT hash FROM event_reminder_hashes
                WHERE event_id = ? AND reminder_type = ?
            """, (event_id, reminder_type))
            row = cursor.fetchone()
            return row[0] if row else None
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при отриманні хешу для події {event_id} ({reminder_type}): {e}")
        return None


def save_event_reminder_hash(event_id: str, reminder_type: str, hash_value: str):
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO event_reminder_hashes (event_id, reminder_type, hash)
                VALUES (?, ?, ?)
                ON CONFLICT(event_id, reminder_type) DO UPDATE SET hash = excluded.hash
            """, (event_id, reminder_type, hash_value))
        logger.info(f"✅ Збережено хеш для події {event_id} ({reminder_type})")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні хешу події {event_id}: {e}")


def update_user_list(list_key: str, user_id: str, add: bool = True):
    """Add or remove a user ID from a JSON list stored in the database."""
    try:
        users_str = get_value(list_key)
        users = json.loads(users_str) if users_str else []
        user_id = str(user_id)
        if add and user_id not in users:
            users.append(user_id)
            set_value(list_key, json.dumps(users))
            logger.info(
                "✅ Додано користувача %s до списку %s",
                mask_user_id(user_id),
                list_key,
            )
        elif not add and user_id in users:
            users.remove(user_id)
            set_value(list_key, json.dumps(users))
            logger.info(
                "✅ Видалено користувача %s зі списку %s",
                mask_user_id(user_id),
                list_key,
            )
        return users
    except Exception as e:
        logger.error(f"❌ Помилка при оновленні списку {list_key}: {e}")
        return []
def add_user_to_list(user_id: str, list_key: str = "bot_users"):
    return update_user_list(list_key, user_id, add=True)


def add_user_to_reminders(user_id: str, list_key: str = "users_with_reminders"):
    return update_user_list(list_key, user_id, add=True)


def remove_user_from_reminders(user_id: str, list_key: str = "users_with_reminders"):
    return update_user_list(list_key, user_id, add=False)


def add_group_to_list(chat_id: str, chat_title: str):
    try:
        groups_str = get_value("group_chats")
        groups = json.loads(groups_str) if groups_str else []
        chat_exists = any(group.get("chat_id") == str(chat_id) for group in groups)
        if not chat_exists:
            groups.append({"chat_id": str(chat_id), "title": chat_title})
            set_value("group_chats", json.dumps(groups))
            logger.info(f"✅ Додано групу {chat_title} (ID: {chat_id}) до списку")
        return groups
    except Exception as e:
        logger.error(
            f"❌ Помилка при додаванні групи {chat_title} (ID: {chat_id}): {e}"
        )
        return []


def save_bot_message(chat_id: str, message_id: int, message_type: str):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO bot_messages (chat_id, message_id, message_type)
                VALUES (?, ?, ?)
            """,
                (chat_id, message_id, message_type),
            )
        logger.info(
            "✅ Збережено повідомлення: chat_id=%s, message_id=%s, type=%s",
            mask_user_id(chat_id),
            message_id,
            message_type,
        )
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні повідомлення: {e}")


def save_group_message_index(
    chat_id: str,
    message_id: int,
    user_id: str,
    username: str | None,
    full_name: str | None,
    message_date: str,
    text: str,
    is_reply: bool = False,
    reply_to_user_id: str | None = None,
):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO group_message_index
                (chat_id, message_id, user_id, username, full_name, message_date, text, is_reply, reply_to_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(chat_id),
                    int(message_id),
                    str(user_id),
                    username,
                    full_name,
                    message_date,
                    text,
                    1 if is_reply else 0,
                    str(reply_to_user_id) if reply_to_user_id else None,
                ),
            )
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при індексації повідомлення групи: {e}")


def cleanup_group_message_index(retention_days: int = 90) -> int:
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM group_message_index
                WHERE datetime(message_date) < datetime('now', ?)
                """,
                (f"-{int(retention_days)} days",),
            )
            deleted = cursor.rowcount if cursor.rowcount is not None else 0
        return int(deleted)
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка очищення group_message_index: {e}")
        return 0


def cleanup_group_knowledge(retention_days: int = 90) -> tuple[int, int, int]:
    deleted_idx = 0
    deleted_emb = 0
    deleted_facts = 0
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM group_message_index
                WHERE datetime(message_date) < datetime('now', ?)
                """,
                (f"-{int(retention_days)} days",),
            )
            deleted_idx = cursor.rowcount if cursor.rowcount is not None else 0
            cursor.execute(
                """
                DELETE FROM group_message_embeddings
                WHERE datetime(created_at) < datetime('now', ?)
                """,
                (f"-{int(retention_days)} days",),
            )
            deleted_emb = cursor.rowcount if cursor.rowcount is not None else 0
            cursor.execute(
                """
                DELETE FROM group_facts
                WHERE datetime(created_at) < datetime('now', ?)
                """,
                (f"-{int(retention_days)} days",),
            )
            deleted_facts = cursor.rowcount if cursor.rowcount is not None else 0
        return int(deleted_idx), int(deleted_emb), int(deleted_facts)
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка очищення знань групи: {e}")
        return 0, 0, 0


def save_group_message_embedding(
    chat_id: str,
    message_id: int,
    embedding: list[float],
    model: str = "text-embedding-3-small",
):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO group_message_embeddings (chat_id, message_id, embedding, model)
                VALUES (?, ?, ?, ?)
                """,
                (str(chat_id), int(message_id), json.dumps(embedding), model),
            )
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка збереження embedding: {e}")


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        na += a * a
        nb += b * b
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def search_group_messages_semantic(
    chat_id: str,
    query_embedding: list[float],
    lookback_days: int = 90,
    limit: int = 20,
    priority_user_id: str | None = None,
):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT i.chat_id, i.message_id, i.user_id, i.username, i.full_name, i.message_date, i.text, e.embedding
                FROM group_message_index i
                JOIN group_message_embeddings e
                  ON i.chat_id = e.chat_id AND i.message_id = e.message_id
                WHERE i.chat_id = ?
                  AND datetime(i.message_date) >= datetime('now', ?)
                ORDER BY datetime(i.message_date) DESC
                LIMIT 1500
                """,
                (str(chat_id), f"-{int(lookback_days)} days"),
            )
            rows = cursor.fetchall()

        scored = []
        for row in rows:
            try:
                emb = json.loads(row["embedding"])
            except Exception:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            score = sim
            if priority_user_id and str(row["user_id"]) == str(priority_user_id):
                score += 0.08
            if score <= 0:
                continue
            scored.append(
                {
                    "chat_id": row["chat_id"],
                    "message_id": row["message_id"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "message_date": row["message_date"],
                    "text": row["text"],
                    "score": round(score, 5),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: int(limit)]
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка семантичного пошуку в групі: {e}")
        return []


def get_recent_group_messages(chat_id: str, days: int = 7, limit: int = 200):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT chat_id, message_id, user_id, username, full_name, message_date, text
                FROM group_message_index
                WHERE chat_id = ?
                  AND datetime(message_date) >= datetime('now', ?)
                ORDER BY datetime(message_date) DESC
                LIMIT ?
                """,
                (str(chat_id), f"-{int(days)} days", int(limit)),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка читання повідомлень групи: {e}")
        return []


def save_group_fact(
    chat_id: str,
    message_id: int,
    user_id: str,
    fact_type: str,
    event_name: str | None = None,
    event_date: str | None = None,
    event_time: str | None = None,
    location: str | None = None,
    responsible: str | None = None,
    deadline: str | None = None,
    details: str | None = None,
    confidence: float = 0.5,
):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO group_facts
                (chat_id, message_id, user_id, fact_type, event_name, event_date, event_time, location, responsible, deadline, details, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(chat_id),
                    int(message_id),
                    str(user_id),
                    fact_type,
                    event_name,
                    event_date,
                    event_time,
                    location,
                    responsible,
                    deadline,
                    details,
                    float(confidence),
                ),
            )
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка збереження факту групи: {e}")


def get_group_facts(chat_id: str, fact_type: str | None = None, days: int = 30, limit: int = 120):
    try:
        with get_cursor() as cursor:
            if fact_type:
                cursor.execute(
                    """
                    SELECT * FROM group_facts
                    WHERE chat_id = ?
                      AND fact_type = ?
                      AND datetime(created_at) >= datetime('now', ?)
                    ORDER BY datetime(created_at) DESC
                    LIMIT ?
                    """,
                    (str(chat_id), fact_type, f"-{int(days)} days", int(limit)),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM group_facts
                    WHERE chat_id = ?
                      AND datetime(created_at) >= datetime('now', ?)
                    ORDER BY datetime(created_at) DESC
                    LIMIT ?
                    """,
                    (str(chat_id), f"-{int(days)} days", int(limit)),
                )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка читання фактів групи: {e}")
        return []


def find_group_conflicts(chat_id: str, days: int = 120):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT lower(trim(event_name)) AS event_key, event_date, COUNT(*) AS cnt
                FROM group_facts
                WHERE chat_id = ?
                  AND fact_type IN ('event', 'performance', 'rehearsal', 'announcement')
                  AND event_name IS NOT NULL
                  AND event_date IS NOT NULL
                  AND datetime(created_at) >= datetime('now', ?)
                GROUP BY event_key, event_date
                """,
                (str(chat_id), f"-{int(days)} days"),
            )
            rows = cursor.fetchall()
        by_event: dict[str, set[str]] = {}
        for row in rows:
            key = row["event_key"]
            dt = row["event_date"]
            by_event.setdefault(key, set()).add(dt)
        conflicts = [k for k, dates in by_event.items() if len(dates) > 1]
        if not conflicts:
            return []
        result = []
        with get_cursor() as cursor:
            for key in conflicts:
                cursor.execute(
                    """
                    SELECT event_name, event_date, message_id, user_id, details, created_at
                    FROM group_facts
                    WHERE chat_id = ?
                      AND lower(trim(event_name)) = ?
                    ORDER BY datetime(created_at) DESC
                    LIMIT 8
                    """,
                    (str(chat_id), key),
                )
                result.append({"event_key": key, "items": [dict(r) for r in cursor.fetchall()]})
        return result
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка пошуку конфліктів фактів: {e}")
        return []


def search_group_messages(
    chat_id: str,
    query: str,
    lookback_days: int = 90,
    limit: int = 40,
    priority_user_id: str | None = None,
):
    try:
        raw_tokens = re.findall(r"[\w\u0400-\u04FF]+", (query or "").lower())
        tokens = [t for t in raw_tokens if len(t) >= 3][:8]
        if not tokens and query:
            tokens = [query.lower().strip()[:64]]
        if not tokens:
            return []

        like_conditions = " OR ".join(["lower(text) LIKE ?" for _ in tokens])
        params = [str(chat_id), f"-{int(lookback_days)} days", *[f"%{t}%" for t in tokens], int(limit * 5)]
        sql = f"""
            SELECT chat_id, message_id, user_id, username, full_name, message_date, text
            FROM group_message_index
            WHERE chat_id = ?
              AND datetime(message_date) >= datetime('now', ?)
              AND ({like_conditions})
            ORDER BY datetime(message_date) DESC
            LIMIT ?
        """
        with get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        scored = []
        for row in rows:
            text_l = (row["text"] or "").lower()
            score = 0
            for token in tokens:
                if token in text_l:
                    score += 2
            if priority_user_id and str(row["user_id"]) == str(priority_user_id):
                score += 5
            if score <= 0:
                continue
            scored.append(
                {
                    "chat_id": row["chat_id"],
                    "message_id": row["message_id"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "message_date": row["message_date"],
                    "text": row["text"],
                    "score": score,
                }
            )

        scored.sort(key=lambda item: (item["score"], item["message_date"]), reverse=True)
        return scored[: int(limit)]
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка пошуку в group_message_index: {e}")
        return []


def migrate_sensitive_values_encryption() -> int:
    if not DB_ENCRYPTION_KEY:
        logger.warning("DB_ENCRYPTION_KEY не задано: шифрування чутливих значень вимкнено.")
        return 0
    changed = 0
    try:
        with get_cursor() as cursor:
            for table in ("users", "groups", "reminders", "persistent_reminders"):
                cursor.execute(f"SELECT key, value FROM {table}")
                rows = cursor.fetchall()
                for row in rows:
                    key = row["key"]
                    value = row["value"]
                    if not _is_sensitive_key(key):
                        continue
                    if not isinstance(value, str) or is_encrypted(value):
                        continue
                    encrypted = encrypt_text(value, DB_ENCRYPTION_KEY)
                    if encrypted != value:
                        cursor.execute(
                            f"UPDATE {table} SET value = ?, updated_at = datetime('now') WHERE key = ?",
                            (encrypted, key),
                        )
                        changed += 1
        if changed:
            logger.info("✅ Міграція шифрування завершена: оновлено %d значень.", changed)
        else:
            logger.info("ℹ️ Міграція шифрування: чутливі значення вже у потрібному стані.")
        return changed
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка міграції шифрування чутливих значень: {e}")
        return 0


def get_users_with_reminders():
    value = get_value("users_with_reminders")
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


__all__ = [
    "init_db",
    "migrate_database",
    "get_value",
    "set_value",
    "delete_value",
    "update_user_list",
    "add_user_to_list",
    "add_user_to_reminders",
    "remove_user_from_reminders",
    "add_group_to_list",
    "create_tables",
    "get_connection",
    "save_bot_message",
    "save_group_message_index",
    "cleanup_group_message_index",
    "cleanup_group_knowledge",
    "search_group_messages",
    "save_group_message_embedding",
    "search_group_messages_semantic",
    "get_recent_group_messages",
    "save_group_fact",
    "get_group_facts",
    "find_group_conflicts",
    "migrate_sensitive_values_encryption",
]

db = type("ReminderDB", (), {
    "get_value": staticmethod(get_value),
    "set_value": staticmethod(set_value),
    "delete_value": staticmethod(delete_value),
    "update_user_list": staticmethod(update_user_list),
    "add_user_to_reminders": staticmethod(add_user_to_reminders),
    "remove_user_from_reminders": staticmethod(remove_user_from_reminders),
    "save_bot_message": staticmethod(save_bot_message),
    "save_group_message_index": staticmethod(save_group_message_index),
    "cleanup_group_message_index": staticmethod(cleanup_group_message_index),
    "cleanup_group_knowledge": staticmethod(cleanup_group_knowledge),
    "search_group_messages": staticmethod(search_group_messages),
    "save_group_message_embedding": staticmethod(save_group_message_embedding),
    "search_group_messages_semantic": staticmethod(search_group_messages_semantic),
    "get_recent_group_messages": staticmethod(get_recent_group_messages),
    "save_group_fact": staticmethod(save_group_fact),
    "get_group_facts": staticmethod(get_group_facts),
    "find_group_conflicts": staticmethod(find_group_conflicts),
    "migrate_sensitive_values_encryption": staticmethod(migrate_sensitive_values_encryption),
    "get_event_reminder_hash": staticmethod(get_event_reminder_hash),
    "get_users_with_reminders": staticmethod(get_users_with_reminders),
    "save_event_reminder_hash": staticmethod(save_event_reminder_hash),
    "add_group_to_list": staticmethod(add_group_to_list),
})()
