import os
from pathlib import Path

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ Укажи BOT_TOKEN в переменных окружения!")
DB_PATH = Path(__file__).parent / "bot.db"
