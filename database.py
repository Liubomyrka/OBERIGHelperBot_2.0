# database.py

import sqlite3
from utils.logger import logger
from typing import Optional

# 🛡️ Підключення до бази даних
def get_connection() -> sqlite3.Connection:
    try:
        connection = sqlite3.connect('bot_data.db')
        connection.row_factory = sqlite3.Row  # Дозволяє доступ до стовпців за іменами
        return connection
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка підключення до бази даних: {e}")
        raise


# 🛡️ Ініціалізація бази даних
def init_db():
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            connection.commit()
            logger.info("✅ База даних ініціалізована.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при ініціалізації бази даних: {e}")


# 🛡️ Збереження значення за ключем
def set_value(key: str, value: str):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('''
                INSERT INTO reminders (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value;
            ''', (key, value))
            connection.commit()
            logger.info(f"✅ Збережено значення для ключа '{key}'.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні значення для ключа '{key}': {e}")


# 🛡️ Отримання значення за ключем
def get_value(key: str) -> Optional[str]:
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT value FROM reminders WHERE key=?', (key,))
            result = cursor.fetchone()
            return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при отриманні значення для ключа '{key}': {e}")
        return None


# 🛡️ Видалення значення за ключем
def delete_value(key: str):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('DELETE FROM reminders WHERE key=?', (key,))
            connection.commit()
            logger.info(f"✅ Видалено значення для ключа '{key}'.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при видаленні значення для ключа '{key}': {e}")

