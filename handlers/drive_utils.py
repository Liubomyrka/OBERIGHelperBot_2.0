import os
import asyncio  # Додаємо імпорт для асинхронної затримки
import io
import json
from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload  # Імпорт для завантаження файлів
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from telegram import InputFile
import tempfile  # Для кросплатформної роботи з тимчасовими файлами
from database import get_value, set_value, save_bot_message
from config import GOOGLE_CREDENTIALS

# Налаштування Google Drive API
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
NOTY_FOLDER_ID = os.getenv(
    "NOTY_FOLDER_ID", "1mLWk6qMDYJ9OtHJPjFA5gI_kTtoUsiIK"
)  # Використовуємо значення з .env.new або дефолт


async def list_sheets(
    update: Update | None = None,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    use_cache: bool = True,
):
    """Отримує список нот із Google Drive, використовуючи кеш за можливістю."""
    try:
        if use_cache:
            cached = get_value("sheet_music_cache")
            if cached:
                logger.info("Список нот взято з кешу бази даних")
                return json.loads(cached)

        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS, scopes=SCOPES
        )
        service = build("drive", "v3", credentials=credentials)

        # Отримуємо файли з папки, де зберігаються ноти (за id або шляхом)
        query = f"mimeType='application/pdf' and '{NOTY_FOLDER_ID}' in parents"
        logger.debug(f"Виконуємо запит до Google Drive з query: {query}")
        results = (
            service.files().list(q=query, fields="files(id, name, parents)").execute()
        )
        items = results.get("files", [])

        logger.debug(
            f"Отримано {len(items)} файлів з Google Drive для папки '{NOTY_FOLDER_ID}'"
        )

        if not items:
            logger.warning("Не знайдено нот у вказаній папці Google Drive.")
            if update:
                await update.message.reply_text(
                    "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
                )
            return {}

        # Групуємо файли за категоріями (наприклад, за першим словом у назві)
        categorized_sheets = {}
        for item in items:
            name_parts = item["name"].split()
            if name_parts:
                category = name_parts[0].lower()
                if category not in categorized_sheets:
                    categorized_sheets[category] = []
                categorized_sheets[category].append(
                    {"id": item["id"], "name": item["name"]}
                )

        # Кешуємо список нот у базі даних
        set_value("sheet_music_cache", json.dumps(categorized_sheets))
        logger.info("Список нот успішно закешовано")

        return categorized_sheets

    except HttpError as error:
        logger.error(f"Помилка при отриманні списку нот з Google Drive: {error}")
        if update:
            await update.message.reply_text(
                "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
            )
        return {}




async def send_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str):
    """
    Надсилає PDF-файл нот з Google Drive.
    """
    try:
        # Перевіряємо, чи є file_id
        if not file_id:
            await update.message.reply_text(
                "❌ Не вказано ідентифікатор файлу. #Оберіг"
            )
            return

        # Автентифікація в Google Drive
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS, scopes=SCOPES
        )
        service = build("drive", "v3", credentials=credentials)

        # Отримуємо метадані файлу
        file_metadata = service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name", "Невідома нота")

        # Завантажуємо файл
        request = service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Скидуємо курсор файлу на початок
        file_content.seek(0)

        # Надсилаємо файл
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=InputFile(file_content, filename=file_name),
            caption=f"🎼 Ось ноти: {file_name} #Оберіг 🌟",
        )

    except HttpError as error:
        logger.error(f"Помилка при отриманні файлу з Google Drive: {error}")
        await update.message.reply_text(
            "❌ Не вдалося завантажити ноти. Спробуйте пізніше. #Оберіг 😕"
        )
    except Exception as e:
        logger.error(f"Невідома помилка при надсиланні нот: {e}")
        await update.message.reply_text(
            "❌ Виникла несподівана помилка. Спробуйте пізніше. #Оберіг 😔"
        )


__all__ = ["list_sheets", "send_sheet"]
