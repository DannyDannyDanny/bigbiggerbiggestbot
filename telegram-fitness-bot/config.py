import os

# Telegram Bot Token — loaded from .env automatically by start.py
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Public HTTPS URL — set automatically by start.py via localtunnel
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080")

# API server settings
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8080"))

# Database path — defaults to fitness.db in the working directory
DB_PATH = os.environ.get("DB_PATH", "fitness.db")
