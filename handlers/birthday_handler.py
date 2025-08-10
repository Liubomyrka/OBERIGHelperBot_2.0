from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger


# 🥳 Команда для вітання з днем народження
async def birthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Надсилає привітання з днем народження без зайвих префіксів."""
    logger.info("🔄 Виконання команди: /birthday")
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("❗ Будь ласка, вкажіть ім'я для привітання.")
        return

    greeting = (
        f"💐 Дорога {name}, вітаємо тебе з днем народження! Нехай кожен день буде "
        "наповнений натхненням і радістю! Ти - справжня зірка нашого хору, і ми "
        "завжди в захопленні від твого таланту! 🎶✨\n\n"
        "Бажаємо здійснення всіх мрій і успіхів у всьому! Із задоволенням чекаємо "
        "нових музичних звершень!\n\n"
        "Зі святом! 🌟🎈 #ЗДнемНародження #ХорОберіг #Оберіг #ДеньНародження"
    )

    sent = await update.message.reply_text(greeting)
    stored_ids = context.chat_data.setdefault("bot_messages", [])
    stored_ids.append(sent.message_id)
    logger.info(f"✅ Надіслано привітання для {name} з message_id {sent.message_id}")


# 🗑️ Команда для видалення останніх повідомлень бота
async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видаляє повідомлення бота, які зберігаються в chat_data."""
    logger.info("🔄 Виконання команди: /clear")
    message_ids = context.chat_data.get("bot_messages", [])
    for mid in message_ids:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            logger.info(f"🗑️ Видалено повідомлення: {mid}")
        except Exception as e:
            logger.error(f"❌ Помилка при видаленні повідомлення {mid}: {e}")
    context.chat_data["bot_messages"] = []
    await update.message.reply_text("🗑️ Повідомлення очищено.")


__all__ = ["birthday_command", "clear_messages"]
