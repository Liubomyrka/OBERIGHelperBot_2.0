from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger
from handlers.drive_utils import list_sheets, send_sheet
from database import get_value, save_bot_message


async def search_notes(
    update: Update, context: ContextTypes.DEFAULT_TYPE, keyword: str = None
):
    """Обробляє пошук нот за ключовим словом і показує клавіатуру з результатами."""
    chat_id = str(update.effective_chat.id)
    if chat_id != "-1001906486581" and update.effective_chat.type != "private":
        return []

    # Якщо ключове слово не вказане, повертаємо порожній список або використовуємо текст повідомлення
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

    # Гнучкий пошук нот за ключовим словом (з урахуванням фрагментів слів і повного тексту)
    results = []
    all_sheets = []
    for category, items in sheets.items():
        all_sheets.extend(items)
    for sheet in all_sheets:
        name_lower = sheet["name"].lower()
        if keyword in name_lower or any(  # Пошук у повному тексті назви
            keyword in part.lower() for part in name_lower.split()
        ):  # Пошук у фрагментах слів
            results.append(sheet)

    if results and update:  # Повертаємо результати лише якщо є оновлення (update)
        # Сортуємо результати за алфавітом для зручності
        results.sort(key=lambda x: x["name"].lower())
        keyboard = []
        for sheet in results[
            :5
        ]:  # Обмежуємо до 5 результатів, щоб уникнути переповнення
            keyboard.append([KeyboardButton(f"📃 {sheet['name']}")])
        keyboard.append([KeyboardButton("🔙 Меню нот")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            "🎵 *Обери ноти внизу* ⬇️", parse_mode="Markdown", reply_markup=reply_markup
        )
        save_bot_message(chat_id, message.message_id, "general")
        logger.info(
            f"✅ Пошук за ключовим словом '{keyword}' виконано з результатами: {len(results)} нот знайдено"
        )
        return results
    elif not results and update:
        message = await update.message.reply_text(
            f"🔍 *Ноти за '{keyword}' не знайдено 😔* Спробуй інше слово! ⬇️",
            parse_mode="Markdown",
        )
        save_bot_message(chat_id, message.message_id, "general")
        logger.info(f"🔍 Нот за ключовим словом '{keyword}' не знайдено")
        return []
    return results


__all__ = ["search_notes"]
