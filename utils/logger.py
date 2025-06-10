import logging
from logging.handlers import RotatingFileHandler
from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, LOG_FILE
import os
import sys

# Створення папки для логів
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Налаштування форматування
formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

# Налаштування обробника файлу
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)

# Налаштування обробника консолі
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Забезпечення підтримки Unicode у Windows-консолі
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Налаштування логера
logger = logging.getLogger("OBERIGHelperBot")
logger.setLevel(LOG_LEVEL)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Перевірка налаштувань логування
logger.info("Логер успішно налаштовано. Логи записуються у консоль і файл.")
