# calendar_utils.py

from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime, timezone, timedelta
from utils.logger import logger
from config import GOOGLE_CREDENTIALS, CALENDAR_ID

# 🛡️ Вимкнення кешування для googleapiclient
import googleapiclient.discovery
googleapiclient.discovery.CACHE = None

# 🛡️ Перевірка наявності файлу облікових даних
if not os.path.exists(GOOGLE_CREDENTIALS):
    raise FileNotFoundError(f"❌ Файл облікових даних Google не знайдено за шляхом: {GOOGLE_CREDENTIALS}")


# 📅 **Отримання списку майбутніх подій**
def get_calendar_events(max_results=10):
    """
    Отримує список майбутніх подій із Google Calendar.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        service = build("calendar", "v3", credentials=credentials)

        now = datetime.now(timezone.utc).isoformat()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            logger.warning("⚠️ Немає запланованих подій у Google Calendar.")
        else:
            logger.info(f"✅ Отримано {len(events)} подій із Google Calendar.")

        return events

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні подій з календаря: {e}")
        return []


# 📅 **Отримання подій на сьогодні**
def get_today_events():
    """
    Отримує події, заплановані на сьогодні.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        service = build("calendar", "v3", credentials=credentials)

        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            logger.info("📅 Сьогодні немає запланованих подій у календарі.")
        else:
            logger.info(f"✅ Отримано {len(events)} подій на сьогодні.")

        return events

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні подій на сьогодні: {e}")
        return []

# 🔔 **Отримання подій для нагадувань (за годину до події)**
def get_upcoming_event_reminders(events, reminder_minutes=60):
    """
    Отримати події, для яких потрібно надіслати нагадування за певний час до події.
    """
    reminders = []
    now = datetime.now(timezone.utc)

    for event in events:
        try:
            start = event["start"].get("dateTime", event["start"].get("date"))

            if 'T' in start:
                start_time = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(timezone.utc)
            else:
                start_time = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc)

            reminder_time = start_time - timedelta(minutes=reminder_minutes)

            if now >= reminder_time and now < start_time:
                reminders.append(event)
                logger.info(f"🔔 Додано нагадування для події: {event.get('summary', 'Без назви')}")

        except ValueError as ve:
            logger.error(f"❌ Неправильний формат дати у події: {event.get('summary', 'Без назви')} - {ve}")
        except Exception as e:
            logger.error(f"❌ Помилка при обробці часу події: {e}")

    logger.info(f"✅ Всього подій для нагадування: {len(reminders)}")
    return reminders


# 📌 **Отримання детальної інформації про подію за її ID**
def get_event_details(event_id: str):
    """
    Отримує детальну інформацію про подію за її ID.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        service = build("calendar", "v3", credentials=credentials)
        
        event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        logger.info(f"✅ Отримано деталі події з ID: {event_id}")
        return event

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні деталей події ({event_id}): {e}")
        return None


# 📺 **Отримання останнього відео з YouTube**
import requests

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")  # Переконайтесь, що ключ додано до .env
YOUTUBE_PLAYLIST_ID = "PLEkdnztUMQ7-05r94OMzHyCVMCXvkgrFn"

def get_latest_youtube_video():
    """
    Отримує останнє відео зі списку YouTube.
    """
    try:
        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=1&playlistId={YOUTUBE_PLAYLIST_ID}&key={YOUTUBE_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if 'items' in data and len(data['items']) > 0:
            video_id = data['items'][0]['snippet']['resourceId']['videoId']
            logger.info(f"✅ Отримано останнє відео з ID: {video_id}")
            return f"https://www.youtube.com/watch?v={video_id}"
        else:
            logger.warning("⚠️ У списку відтворення немає відео.")
            return None
    except Exception as e:
        logger.error(f"❌ Помилка при отриманні останнього відео: {e}")
        return None


# 🛡️ **Експортуємо функції для доступу**
___all__ = [
    'get_calendar_events',
    'get_today_events',
    'get_upcoming_event_reminders',
    'get_event_details',
    'get_latest_youtube_video'  # Додано нову функцію
]
