from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger
from handlers.drive_utils import list_sheets
from database import get_value, save_bot_message
import json


async def search_notes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str | None = None,
    next_page: bool = False,
):
    """Пошук нот за ключовим словом з підтримкою пагінації (5 елементів на сторінку)."""
    chat_id = str(update.effective_chat.id)
    if update.effective_chat.type != "private":
        return []

    # Якщо ключове слово не вказане, намагаємося взяти його з тексту повідомлення
    if not keyword and update.message and update.message.text:
        keyword = update.message.text.lower()
    elif not keyword:
        return []

    keyword = keyword.lower()
    logger.info(f"🔍 Пошук нот за ключовим словом: {keyword}")

    # Спочатку перевіряємо кеш у базі даних
    cached_sheets = get_value("sheet_music_cache")
    if cached_sheets:
        sheets = json.loads(cached_sheets)
        logger.info("Список нот взято з кешу бази даних")
    else:
        # Якщо кешу немає, звертаємося до Google Drive
        sheets = await list_sheets(update, context)
        if not sheets:
            if update:
                await update.message.reply_text(
                    "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
                )
            return []

    # Пошук нот за ключовим словом
    all_sheets: list[dict] = []
    for items in sheets.values():
        all_sheets.extend(items)
    results = [s for s in all_sheets if keyword in s["name"].lower()]

    if not results:
        if update:
            message = await update.message.reply_text(
                f"🔍 *Ноти за '{keyword}' не знайдено 😔* Спробуй інше слово! ⬇️",
                parse_mode="Markdown",
            )
            save_bot_message(chat_id, message.message_id, "general")
        logger.info(f"🔍 Нот за ключовим словом '{keyword}' не знайдено")
        return []

    # Сортуємо результати за алфавітом
    results.sort(key=lambda x: x["name"].lower())

    # Якщо це новий пошук або змінене ключове слово, зберігаємо його
    if not next_page or context.user_data.get("last_search_keyword") != keyword:
        context.user_data["last_search_keyword"] = keyword
        context.user_data["search_results"] = results
        context.user_data["search_offset"] = 0

    stored = context.user_data.get("search_results", [])
    offset = context.user_data.get("search_offset", 0)
    page = stored[offset : offset + 5]
    context.user_data["search_offset"] = offset + len(page)

    if update:
        keyboard = [[KeyboardButton(f"📃 {sheet['name']}")] for sheet in page]
        if context.user_data["search_offset"] < len(stored):
            keyboard.append([KeyboardButton("➡️ Ще результати")])
        keyboard.append([KeyboardButton("🔙 Меню нот")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            "🎵 *Обери ноти внизу* ⬇️",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        save_bot_message(chat_id, message.message_id, "general")
        logger.info(
            f"✅ Пошук за ключовим словом '{keyword}' повернув {len(stored)} результатів"
        )

    return page


__all__ = ["search_notes"]
