from google.oauth2 import service_account
from googleapiclient.discovery import build
from utils.youtube_utils import get_youtube_service
import os
from datetime import datetime
import pytz
from utils.logger import logger
from config import GOOGLE_CREDENTIALS, CALENDAR_ID, YOUTUBE_API_KEY, OBERIG_PLAYLIST_ID
from googleapiclient.errors import HttpError
from database import get_value, set_value, get_cursor
import json
import re

# Вимкнення кешування для googleapiclient
import googleapiclient.discovery

googleapiclient.discovery.CACHE = None

# Перевірка наявності файлу облікових даних
if not os.path.exists(GOOGLE_CREDENTIALS):
    raise FileNotFoundError(
        f"Файл облікових даних Google не знайдено за шляхом: {GOOGLE_CREDENTIALS}"
    )

BERLIN_TZ = pytz.timezone("Europe/Berlin")


# Отримання списку майбутніх подій
def get_calendar_events(max_results=150):
    """
    Отримує список майбутніх подій із Google Calendar.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service = build("calendar", "v3", credentials=credentials)

        now = datetime.now(BERLIN_TZ).isoformat()
        events_result = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=now,
                maxResults=max_results,  # Збільшено до 150 подій
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            logger.warning("Немає запланованих подій у Google Calendar.")
        else:
            logger.info(f"Отримано {len(events)} подій із Google Calendar.")

        return events

    except Exception as e:
        logger.error(f"Помилка при отриманні подій з календаря: {e}")
        return []


# Отримання подій на сьогодні
def get_today_events():
    """
    Отримує події, заплановані на сьогодні за берлінським часом.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service = build("calendar", "v3", credentials=credentials)

        now = datetime.now(BERLIN_TZ)
        start_of_day = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(BERLIN_TZ)
            .isoformat()
        )
        end_of_day = (
            now.replace(hour=23, minute=59, second=59, microsecond=999999)
            .astimezone(BERLIN_TZ)
            .isoformat()
        )

        events_result = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=start_of_day,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])
        today_events = []
        today_date = now.date()

        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            if "T" in start:
                start_dt = datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                ).astimezone(BERLIN_TZ)
                event_date = start_dt.date()
            else:
                event_date = datetime.strptime(start, "%Y-%m-%d").date()

            if event_date == today_date:
                today_events.append(event)

        if not today_events:
            logger.info("Сьогодні немає запланованих подій у календарі.")
        else:
            logger.info(f"Отримано {len(today_events)} подій на сьогодні.")

        return today_events

    except Exception as e:
        logger.error(f"Помилка при отриманні подій на сьогодні: {e}")
        return []


# Отримання подій для нагадувань (за годину до події)
def get_upcoming_event_reminders(events, reminder_minutes=60):
    """
    Отримати події, для яких потрібно надіслати нагадування за певний час до події.
    """
    reminders = []
    now = datetime.now(BERLIN_TZ)

    for event in events:
        try:
            start = event["start"].get("dateTime", event["start"].get("date"))

            if "T" in start:
                start_time = datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                ).astimezone(BERLIN_TZ)
            else:
                start_time = datetime.strptime(start, "%Y-%m-%d").replace(
                    tzinfo=BERLIN_TZ
                )

            reminder_time = start_time - timedelta(minutes=reminder_minutes)

            if now >= reminder_time and now < start_time:
                reminders.append(event)
                logger.info(
                    f"Додано нагадування для події: {event.get('summary', 'Без назви')}"
                )

        except ValueError as ve:
            logger.error(
                f"Неправильний формат дати у події: {event.get('summary', 'Без назви')} - {ve}"
            )
        except Exception as e:
            logger.error(f"Помилка при обробці часу події: {e}")

    logger.info(f"Всього подій для нагадування: {len(reminders)}")
    return reminders


# Отримання детальної інформації про подію за її ID
def get_event_details(event_id: str):
    """
    Отримує детальну інформацію про подію за її ID і повертає відформатований текст із підтримкою HTML для Telegram.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service = build("calendar", "v3", credentials=credentials)

        event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        logger.info(f"Отримано деталі події з ID: {event_id}")

        summary = event.get("summary", "Без назви")
        start = event.get("start", {}).get(
            "dateTime", event.get("start", {}).get("date", "")
        )
        end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
        location = event.get("location", "Місце не вказано")
        description = event.get("description", "Опис відсутній")

        tz = BERLIN_TZ
        if "T" in start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(
                tz
            )
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(tz)
            time_format = f"{start_dt.strftime('%d-%m-%Y')}\n⏰ {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        else:
            start_dt = datetime.fromisoformat(start).replace(tzinfo=tz)
            time_format = f"{start_dt.strftime('%d-%m-%Y')} (повноденна подія)"

        if description:
            html_to_telegram = {
                "<b>": "<b>",
                "</b>": "</b>",
                "<i>": "<i>",
                "</i>": "</i>",
                "<u>": "<u>",
                "</u>": "</u>",
                "<strong>": "<b>",
                "</strong>": "</b>",
                "<em>": "<i>",
                "</em>": "</i>",
                "<p>": "",
                "</p>": "\n",
                "<br>": "\n",
                "<h1>": "<b>",
                "</h1>": "</b>\n",
                "<h2>": "<b>",
                "</h2>": "</b>\n",
                "<h3>": "<b>",
                "</h3>": "</b>\n",
                "<ul>": "",
                "</ul>": "",
                "<li>": "• ",
                "</li>": "\n",
                "<strike>": "<s>",
                "</strike>": "</s>",
                "<del>": "<s>",
                "</del>": "</s>",
            }

            for html_tag, telegram_tag in html_to_telegram.items():
                description = description.replace(html_tag, telegram_tag)

            description = re.sub(r"</?.*?>", "", description)

        return {
            "summary": summary,
            "time": time_format,
            "location": location,
            "description": description,
        }
    except Exception as e:
        logger.error(f"Помилка при отриманні деталей події {event_id}: {e}")
        return None


# Отримання найновішого відео з плейліста YouTube
def get_latest_youtube_video():
    """
    Отримує посилання на найновше відео за датою публікації з плейліста YouTube.
    """
    try:
        youtube = get_youtube_service()

        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=OBERIG_PLAYLIST_ID,
            maxResults=50,
        )
        response = request.execute()

        if not response.get("items"):
            logger.warning("Немає доступних відео в плейлісті.")
            return None

        latest_video = None
        latest_date = None

        for item in response["items"]:
            try:
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_response = (
                    youtube.videos().list(part="snippet", id=video_id).execute()
                )

                if video_response.get("items"):
                    publish_date = video_response["items"][0]["snippet"]["publishedAt"]
                    if latest_date is None or publish_date > latest_date:
                        latest_date = publish_date
                        latest_video = video_id
            except Exception as e:
                logger.warning(
                    f"Помилка при отриманні інформації про відео {video_id}: {e}"
                )
                continue

        if latest_video:
            video_url = f"https://www.youtube.com/watch?v={latest_video}"
            logger.info(f"Найновше відео за датою публікації отримано: {video_url}")
            return video_url
        else:
            logger.warning("Не вдалося знайти найновше відео.")
            return None

    except HttpError as e:
        logger.error(f"Помилка при отриманні найновішого відео: {e}")
        return None


# Отримання найпопулярнішого відео з плейліста YouTube
def get_most_popular_youtube_video():
    """
    Отримує посилання на найпопулярніше відео з плейліста YouTube.
    """
    try:
        youtube = get_youtube_service()

        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=OBERIG_PLAYLIST_ID,
            maxResults=50,
        )
        response = request.execute()

        if not response.get("items"):
            logger.warning("Немає доступних відео в плейлісті.")
            return None

        most_popular_video = None
        max_views = 0

        for item in response["items"]:
            try:
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_response = (
                    youtube.videos().list(part="statistics", id=video_id).execute()
                )

                if video_response.get("items"):
                    view_count = int(
                        video_response["items"][0]["statistics"]["viewCount"]
                    )
                    if view_count > max_views:
                        max_views = view_count
                        most_popular_video = video_id
            except Exception as e:
                logger.warning(
                    f"Помилка при отриманні статистики відео {video_id}: {e}"
                )
                continue

        if most_popular_video:
            video_url = f"https://www.youtube.com/watch?v={most_popular_video}"
            logger.info(f"Найпопулярніше відео отримано: {video_url}")
            return video_url
        else:
            logger.warning("Не вдалося знайти найпопулярніше відео.")
            return None

    except Exception as e:
        logger.error(f"Помилка при отриманні найпопулярнішого відео: {e}")
        return None


# Отримання списку 5 найпопулярніших відео з плейліста YouTube
# utils/calendar_utils.py
def get_top_10_videos():  # Змінюємо назву
    """
    Отримує список 10 найпопулярніших відео з плейліста YouTube.
    Повертає список кортежів (назва, url, кількість переглядів).
    """
    try:
        youtube = get_youtube_service()

        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=OBERIG_PLAYLIST_ID,
            maxResults=50,
        )
        response = request.execute()

        if not response.get("items"):
            logger.warning("Немає доступних відео в плейлісті.")
            return []

        videos = []
        for item in response["items"]:
            try:
                video_id = item["snippet"]["resourceId"]["videoId"]
                title = item["snippet"]["title"]
                video_response = (
                    youtube.videos().list(part="statistics", id=video_id).execute()
                )

                if video_response.get("items"):
                    view_count = int(
                        video_response["items"][0]["statistics"]["viewCount"]
                    )
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    videos.append((title, url, view_count))
            except Exception as e:
                logger.warning(
                    f"Помилка при отриманні статистики відео {video_id}: {e}"
                )
                continue

        videos.sort(key=lambda x: x[2], reverse=True)
        top_10 = videos[:10]  # Змінюємо на 10

        logger.info(f"Отримано топ-10 відео")
        return top_10

    except Exception as e:
        logger.error(f"Помилка при отриманні топ-10 відео: {e}")
        return []

# Перевірка нових відео в плейлісті YouTube
async def check_new_videos():
    """
    Перевіряє наявність нових відео в плейлісті YouTube.
    Повертає список нових відео у форматі [{'video_id': ..., 'title': ..., 'url': ...}].
    """
    try:
        last_known_video_id = get_value("last_known_video")
        last_known_video_id = last_known_video_id if last_known_video_id else ""

        # Отримуємо час останньої перевірки
        last_check_str = get_value("last_video_check")
        last_check = (
            datetime.fromisoformat(last_check_str.replace("Z", "+00:00"))
            if last_check_str and last_check_str != "None"
            else None
        )
        now = datetime.now(BERLIN_TZ)

        youtube = get_youtube_service()

        request = youtube.playlistItems().list(
            part="snippet", playlistId=OBERIG_PLAYLIST_ID, maxResults=10
        )
        response = request.execute()

        new_videos = []

        with get_cursor() as cursor:
            for item in response.get("items", []):
                video_id = item["snippet"]["resourceId"]["videoId"]
                title = item["snippet"]["title"]
                url = f"https://youtu.be/{video_id}"
                publish_date = item["snippet"]["publishedAt"]
                publish_dt = datetime.fromisoformat(
                    publish_date.replace("Z", "+00:00")
                ).astimezone(BERLIN_TZ)

                cursor.execute(
                    "SELECT COUNT(*) FROM sent_notifications WHERE video_id = ?",
                    (video_id,),
                )
                count = cursor.fetchone()[0]

                # Надсилаємо лише якщо відео не надсилалося і опубліковане після останньої перевірки
                if count == 0 and (last_check is None or publish_dt > last_check):
                    new_video_info = {"video_id": video_id, "title": title, "url": url}
                    new_videos.append(new_video_info)
                elif video_id == last_known_video_id:
                    break

        if new_videos:
            latest_video_id = new_videos[0]["video_id"]
            set_value("last_known_video", latest_video_id)
            logger.info(f"Оновлено ID останнього відомого відео: {latest_video_id}")

        # Оновлюємо час останньої перевірки
        set_value("last_video_check", now.isoformat())
        logger.info(f"Оновлено час останньої перевірки відео: {now.isoformat()}")

        return new_videos

    except Exception as e:
        logger.error(f"Помилка при перевірці нових відео: {e}")
        return []


# Експортуємо функції для доступу
__all__ = [
    "get_calendar_events",
    "get_today_events",
    "get_upcoming_event_reminders",
    "get_event_details",
    "get_latest_youtube_video",
    "get_most_popular_youtube_video",
    "get_top_10_videos",  # Оновлюємо
    "check_new_videos",
]