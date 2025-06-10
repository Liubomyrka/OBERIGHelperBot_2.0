import os
from dotenv import load_dotenv

# Завантажуємо змінні оточення з .env
load_dotenv()

# Отримуємо токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не вказано у файлі .env")

# Отримуємо шлях до файлу з обліковими даними Google
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
if not GOOGLE_CREDENTIALS:
    raise ValueError("GOOGLE_CREDENTIALS не вказано у файлі .env")

# Отримуємо ID календаря
CALENDAR_ID = os.getenv("CALENDAR_ID")
if not CALENDAR_ID:
    raise ValueError("CALENDAR_ID не вказано у файлі .env")

# Отримуємо часовий пояс
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
if not os.getenv("TIMEZONE"):
    print(
        "TIMEZONE не вказано у .env файлі. Використовується значення за замовчуванням: Europe/Berlin"
    )

# Налаштування логування
import logging
LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "bot.log"

# ID адміністратора
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
if not ADMIN_ID:
    print("ADMIN_CHAT_ID не вказано у .env файлі")

# Налаштування бази даних
DATABASE_FILE = "bot_data.db"

# Отримуємо API ключ для YouTube
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY не вказано у файлі .env")

# Отримуємо ID плейліста OBERIG
OBERIG_PLAYLIST_ID = os.getenv("OBERIG_PLAYLIST_ID")
if not OBERIG_PLAYLIST_ID:
    raise ValueError("OBERIG_PLAYLIST_ID не вказано у файлі .env")

# Логування завантажених змінних (безпечно)
print(f"TELEGRAM_TOKEN ✅ Конфігурація успішно завантажена.")
print(f"GOOGLE_CREDENTIALS: ✅ Конфігурація успішно завантажена.")
print(f"CALENDAR_ID: ✅ Конфігурація успішно завантажена.")
print(f"TIMEZONE: {TIMEZONE}")
print(f"YOUTUBE_API_KEY: ✅ Конфігурація успішно завантажена.")
print(f"OBERIG_PLAYLIST_ID: {OBERIG_PLAYLIST_ID}")
