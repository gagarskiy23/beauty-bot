import os
from pathlib import Path

BOT_TOKEN = os.getenv("BOT_TOKEN", "8856041679:AAGvxYSm0_IjjN_-k_iAG1zGIdNhvONfrcw")
DB_PATH = Path(__file__).parent / "bot.db"
