import logging
from logging.handlers import RotatingFileHandler
from config import LOG_LEVEL
import os
import sys

# 🛡️ Створення папки для логів
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

# 🛡️ Загальні налаштування форматування
log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)

# 🛡️ Консольний обробник (з кодуванням UTF-8)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(LOG_LEVEL)
console_handler.setFormatter(log_formatter)

# 🔄 Забезпечення підтримки Unicode у Windows-консолі
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 🛡️ Файловий обробник (з ротацією файлів, кодування UTF-8)
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'bot.log'),
    maxBytes=5 * 1024 * 1024,  # Максимальний розмір файлу – 5MB
    backupCount=5,  # Зберігати до 5 старих логів
    encoding='utf-8'  # Встановлюємо UTF-8 для файлів логів
)
file_handler.setLevel('DEBUG')  # Усі рівні логування для файлу
file_handler.setFormatter(log_formatter)

# 🛡️ Ініціалізація логера
logger = logging.getLogger('OBERIG_BOT')
logger.setLevel(LOG_LEVEL)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 🛡️ Перевірка налаштувань логування
logger.info("✅ Логер успішно налаштовано. Логи записуються у консоль і файл.")
