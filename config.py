# config.py

import os
from dotenv import load_dotenv

# Завантаження змінних із .env
load_dotenv()

# Читання змінних середовища
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
REMINDER_CHAT_ID = os.getenv("REMINDER_CHAT_ID")
CALENDAR_ID = os.getenv("CALENDAR_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Перевірка наявності обов'язкових змінних
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не встановлено у .env файлі")
if not GOOGLE_CREDENTIALS:
    raise ValueError("❌ GOOGLE_CREDENTIALS не встановлено у .env файлі")
if not CALENDAR_ID:
    raise ValueError("❌ CALENDAR_ID не встановлено у .env файлі")
if not REMINDER_CHAT_ID:
    raise ValueError("❌ REMINDER_CHAT_ID не встановлено у .env файлі")
