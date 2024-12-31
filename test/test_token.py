import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_TOKEN")

if token:
    print(f"✅ TELEGRAM_TOKEN валідний: {token}")
else:
    print("❌ TELEGRAM_TOKEN недійсний або не знайдений.")
