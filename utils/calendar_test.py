from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime, timezone

CREDENTIALS_FILE = os.path.abspath("oberig_credentials.json")
CALENDAR_ID = "3d1200d4f604504fd92ebc97ccf35ab40d52e1b014a79f9a0b4c61c0ec8dda0c@group.calendar.google.com"

credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/calendar.readonly"]
)

service = build("calendar", "v3", credentials=credentials)

now = datetime.now(timezone.utc).isoformat()
events_result = service.events().list(
    calendarId=CALENDAR_ID,
    timeMin=now,
    maxResults=10,
    singleEvents=True,
    orderBy="startTime"
).execute()

events = events_result.get("items", [])

if not events:
    print("✅ Немає запланованих подій.")
else:
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(f"📌 {start} - {event['summary']}")
