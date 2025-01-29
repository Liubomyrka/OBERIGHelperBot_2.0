import os
from dotenv import load_dotenv

# 🛡️ Завантаження змінних із .env
load_dotenv()

# 🛡️ Читання змінних середовища
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
CALENDAR_ID = os.getenv("CALENDAR_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")  # ✅ Додано TIMEZONE з дефолтним значенням

# 🛡️ Перевірка наявності обов'язкових змінних
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не встановлено у .env файлі")
if not GOOGLE_CREDENTIALS:
    raise ValueError("❌ GOOGLE_CREDENTIALS не встановлено у .env файлі")
if not CALENDAR_ID:
    raise ValueError("❌ CALENDAR_ID не встановлено у .env файлі")

# 🛡️ Логування попередження, якщо TIMEZONE використовує значення за замовчуванням
if TIMEZONE == "Europe/Berlin":
    print("⚠️ TIMEZONE не вказано у .env файлі. Використовується значення за замовчуванням: Europe/Berlin")

# 🛡️ Логування завантажених змінних (безпечно)
print(f"✅ TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:5]}***")
print(f"✅ GOOGLE_CREDENTIALS: {GOOGLE_CREDENTIALS}")
print(f"✅ CALENDAR_ID: {CALENDAR_ID}")
print(f"✅ TIMEZONE: {TIMEZONE}")
