import logging
import re
from logging.handlers import RotatingFileHandler
from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, LOG_FILE
import os
import sys

# Створення папки для логів
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Налаштування форматування
formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

"""
Route logs to logs/<LOG_FILE> with rotation to prevent uncontrolled growth.
"""
file_path = os.path.join(LOG_DIR, LOG_FILE) if not os.path.isabs(LOG_FILE) else LOG_FILE
file_handler = RotatingFileHandler(file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(formatter)

# Налаштування обробника консолі
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Забезпечення підтримки Unicode у Windows-консолі без підміни потоків
if sys.platform == "win32":
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Якщо потік не підтримує переконфігурацію (наприклад, у тестах),
                # просто пропускаємо, щоб не зашкодити механізмам перехоплення.
                pass

_SENSITIVE_PATTERNS = [
    re.compile(r"(/bot)(\d+:[A-Za-z0-9_-]+)"),
    re.compile(r"\b(sk-)[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(AIza)[A-Za-z0-9_-]{20,}\b"),
]


def _mask_sensitive(value):
    if not isinstance(value, str):
        return value
    masked = value
    for pattern in _SENSITIVE_PATTERNS:
        masked = pattern.sub(lambda m: f"{m.group(1)}***", masked)
    return masked


class _SensitiveDataFilter(logging.Filter):
    """Mask well-known secrets (Telegram, OpenAI, Google) in log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _mask_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(_mask_sensitive(arg) for arg in record.args)
            elif isinstance(record.args, dict):
                record.args = {
                    key: _mask_sensitive(value)
                    for key, value in record.args.items()
                }
            else:
                record.args = _mask_sensitive(record.args)
        return True

# Налаштування логера
logger = logging.getLogger("OBERIGHelperBot")
logger.setLevel(LOG_LEVEL)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.addFilter(_SensitiveDataFilter())

# Перевірка налаштувань логування
logger.info("Логер налаштовано. Консоль + ротація файлу логів у 'logs'.")
