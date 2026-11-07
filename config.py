import os
from dotenv import load_dotenv

load_dotenv()

COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()

# Each character has a separate Discord application and bot token.
CHARACTER_TOKENS = {
    "sayori": os.getenv("SAYORI_TOKEN", "").strip(),
    "natsuki": os.getenv("NATSUKI_TOKEN", "").strip(),
    "yuri": os.getenv("YURI_TOKEN", "").strip(),
    "monika": os.getenv("MONIKA_TOKEN", "").strip(),
}

CHARACTERS = tuple(CHARACTER_TOKENS)
