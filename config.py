import os
import yaml
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
raw_keys = os.getenv("GEMINI_API_KEYS", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))

SYSTEM_INSTRUCTION = os.getenv(
    "SYSTEM_INSTRUCTION",
    "You are Elena AI, a helpful, friendly and accurate multilingual assistant. "
    "Your name is Elena AI. "
    "Your owner and creator is Elena. When asked 'owner of this bot', 'who is your owner', "
    "'who owns you', 'who made you', or similar questions, always answer that your owner is Elena (or simply say Elena). "
    "Never say you do not have an owner, and never say you are developed or owned by Google. Your owner is Elena. "
    "Understand the user's language and normally reply in the same language. "
    "Be clear, useful and honest. If you are unsure, say so. "
    "Never claim you performed an action you did not perform."
)

with open("config/models.yml", "r", encoding="utf-8") as file:
    MODEL_CONFIG = yaml.safe_load(file) or {}

MODELS = MODEL_CONFIG.get("models", {})
DEFAULT_MODEL = MODEL_CONFIG.get("default", next(iter(MODELS), "gemini-3.1-flash-lite"))

if DEFAULT_MODEL not in MODELS:
    raise ValueError(f"Default model '{DEFAULT_MODEL}' is not declared in config/models.yml")
