from google.oauth2 import service_account
from googleapiclient.discovery import build
import os

# Шлях до JSON-файлу
CREDENTIALS_FILE = os.path.abspath("oberig_credentials.json")

# Ініціалізація Google Calendar API
credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/calendar.readonly"]
)

service = build("calendar", "v3", credentials=credentials)

# Отримання списку календарів
print("📅 Отримання списку календарів...")
calendar_list = service.calendarList().list().execute()

for calendar in calendar_list['items']:
    print(f"📖 Назва: {calendar['summary']}")
    print(f"🆔 ID: {calendar['id']}")
    print("-" * 30)
