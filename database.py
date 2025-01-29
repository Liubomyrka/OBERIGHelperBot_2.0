# database.py

import sqlite3
import os
from utils.logger import logger
from typing import Optional

# 🛡️ Конфігурація шляху до бази даних
DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_data.db')

# 🛡️ Підключення до бази даних
def get_connection() -> sqlite3.Connection:
    try:
        logger.info(f"🔗 Підключення до бази даних: {DB_PATH}")
        connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        connection.row_factory = sqlite3.Row  # Доступ до стовпців за іменами
        logger.info("✅ Підключення до бази даних успішне.")
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
            logger.info(f"✅ Збережено значення для ключа '{key}' зі значенням '{value}'.")
    except sqlite3.Error as e:
        logger.error(f"❌ Помилка при збереженні значення для ключа '{key}': {e}")

# 🛡️ Отримання значення за ключем
def get_value(key: str) -> Optional[str]:
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT value FROM reminders WHERE key=?', (key,))
            result = cursor.fetchone()
            if result:
                logger.info(f"✅ Отримано значення для ключа '{key}': {result[0]}")
            else:
                logger.info(f"⚠️ Значення для ключа '{key}' не знайдено.")
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
