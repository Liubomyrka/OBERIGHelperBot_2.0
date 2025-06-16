import sqlite3
import os
import json
from utils.logger import logger
from typing import Optional
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
_conn = None


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
                    greeting_text TEXT
                )
                """
            )
            cursor.execute("PRAGMA table_info(birthday_greetings);")
            columns = [col[1] for col in cursor.fetchall()]
            if "greeting_text" not in columns:
                cursor.execute("ALTER TABLE birthday_greetings ADD COLUMN greeting_text TEXT")
                logger.info("✅ Додано колонку greeting_text до birthday_greetings")

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
            cursor.execute(f"""
                INSERT OR REPLACE INTO {table} (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (key, value))
        logger.info(f"✅ Збережено значення для ключа {key} в таблиці {table}")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні значення для ключа {key}: {e}")


def get_value(key: str) -> Optional[str]:
    try:
        with get_cursor() as cursor:
            table = "reminders"
            if key.startswith(("bot_users", "video_notifications_disabled", "users_", "last_video_check")):
                table = "users"
            elif key.startswith(("group_chats", "group_notifications_disabled")):
                table = "groups"
            elif key.startswith(("sent_reminders_persistent", "persistent_", "sent_videos", "users_with_reminders")) or "reminder" in key.lower() or "persistent" in key.lower():
                table = "persistent_reminders"
            cursor.execute(f"SELECT value FROM {table} WHERE key=?", (key,))
            result = cursor.fetchone()
            return result[0] if result else None
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
            logger.info(f"✅ Додано користувача {user_id} до списку {list_key}")
        elif not add and user_id in users:
            users.remove(user_id)
            set_value(list_key, json.dumps(users))
            logger.info(f"✅ Видалено користувача {user_id} зі списку {list_key}")
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
            f"✅ Збережено повідомлення: chat_id={chat_id}, message_id={message_id}, type={message_type}"
        )
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні повідомлення: {e}")


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
]

db = type("ReminderDB", (), {
    "get_value": staticmethod(get_value),
    "set_value": staticmethod(set_value),
    "delete_value": staticmethod(delete_value),
    "update_user_list": staticmethod(update_user_list),
    "add_user_to_reminders": staticmethod(add_user_to_reminders),
    "remove_user_from_reminders": staticmethod(remove_user_from_reminders),
    "save_bot_message": staticmethod(save_bot_message),
    "get_event_reminder_hash": staticmethod(get_event_reminder_hash),
    "get_users_with_reminders": staticmethod(get_users_with_reminders),
    "save_event_reminder_hash": staticmethod(save_event_reminder_hash),
    "add_group_to_list": staticmethod(add_group_to_list),
})()
