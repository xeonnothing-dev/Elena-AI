# Elena AI — Gemini Telegram Chatbot

A multilingual Telegram chatbot powered only by the Google Gemini API.

## Features

- Text conversations in many languages
- Per-user conversation history stored in PostgreSQL
- Model selection with `/settings`
- `/start`, `/help`, `/new`, `/clear`
- Image understanding
- Voice/audio understanding and responses
- Private chats and group chats (in groups, reply to the bot or mention it)
- Models configured in `config/models.yml`

## Requirements

- Python 3.10+
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

Google AI Plus is a consumer subscription and does not automatically include Gemini API credits. API quotas and billing are separate.

## Windows setup (PowerShell)

```powershell
cd xeon-ai
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Put your real `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` in `.env`.
Set `DATABASE_URL` to your PostgreSQL connection string, and create the database
before starting the bot.

Then run:

```powershell
python bot.py
```

## Linux / VPS setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

## Telegram commands

- `/start` — start the bot
- `/help` — show help
- `/settings` — select a configured Gemini model
- `/new` — start a fresh conversation
- `/clear` — delete your saved conversation history

## Add or remove models

Edit `config/models.yml`. The model ID must be available to your Gemini API key. Restart the bot after editing.

## Group chats

For privacy and to avoid unsolicited replies, the bot responds in groups only when a user replies to one of its messages or mentions its username. If the bot does not receive normal group messages, check its privacy mode with BotFather.

## Important notes

- Do not commit `.env` or share API keys.
- The database stores conversation text. Secure access to your PostgreSQL server and database.
- Voice handling sends the audio bytes to Gemini for understanding; it is not a separate Whisper transcription service.
- This starter does not include image generation. That can be added after confirming which image-generation models are available to your API key.
- Telegram and Gemini API usage may have quotas, rate limits, and costs.
