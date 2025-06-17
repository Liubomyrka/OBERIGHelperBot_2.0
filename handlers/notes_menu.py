from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from utils.logger import logger
from .drive_utils import list_sheets, send_sheet
from database import save_bot_message

from .user_utils import auto_add_user

async def show_notes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує початкове меню нот із клавіатурою."""
    chat_id = str(update.effective_chat.id)
    if update.effective_chat.type != "private":
        return

    keyboard = [
        [KeyboardButton("📋 Всі ноти"), KeyboardButton("🔤 За назвою")],
        [KeyboardButton("🔍 За ключовим словом"), KeyboardButton("🔙 Головне меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    message = await update.message.reply_text(
        "🎵 *Обери ноти внизу* ⬇️",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Відображено початкове меню нот")


async def show_all_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує список усіх нот із клавіатурою."""
    chat_id = str(update.effective_chat.id)
    if update.effective_chat.type != "private":
        return

    sheets = await list_sheets(update, context)
    if not sheets:
        await update.message.reply_text("❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️")
        return

    keyboard = []
    all_sheets = []
    for category, items in sheets.items():
        all_sheets.extend(items)
    all_sheets.sort(key=lambda x: x["name"].lower())

    for sheet in all_sheets:
        keyboard.append([KeyboardButton(f"📃 {sheet['name']}")])

    keyboard.append([KeyboardButton("🔙 Меню нот")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    message = await update.message.reply_text(
        "🎵 *Вибери ноти внизу* ⬇️",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Відображено список усіх нот")


async def show_notes_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Застаріла функція, що викликає ``show_all_notes``."""
    await show_all_notes(update, context)


async def get_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє команду /get_sheet для надсилання нот з Google Drive."""
    await auto_add_user(update, context)

    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Вкажіть номер файлу з попереднього списку. Наприклад, /get_sheet 1"
        )
        return

    try:
        file_number = context.args[0].strip(".")

        if not file_number.isdigit():
            await update.message.reply_text(
                "❌ Номер файлу має бути цілим числом. Наприклад, /get_sheet 1"
            )
            return

        sheets = await list_sheets(update, context)
        if not sheets:
            await update.message.reply_text(
                "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
            )
            return

        all_sheets = []
        for category, items in sheets.items():
            all_sheets.extend(items)

        index = int(file_number) - 1
        if index < 0 or index >= len(all_sheets):
            await update.message.reply_text(
                f"❌ Номер файлу має бути від 1 до {len(all_sheets)}"
            )
            return

        sheet = all_sheets[index]
        await send_sheet(update, context, sheet["id"])

    except Exception as e:
        logger.error(f"Помилка при отриманні нот: {e}")
        await update.message.reply_text(
            "❌ Виникла несподівана помилка. Спробуйте пізніше. #Оберіг 😔"
        )


__all__ = [
    "show_notes_menu",
    "show_all_notes",
    "get_sheet_command",
]
