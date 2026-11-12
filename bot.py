import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)
from config import TELEGRAM_BOT_TOKEN, DEFAULT_MODEL, MODELS, MAX_HISTORY
from database import init_db, get_model, set_model, get_history, add_message, clear_history
from gemini import ask_gemini, ask_gemini_with_media

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("elena-ai")


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Elena AI is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Silence Render health ping logs
        pass


def start_health_server():
    port_str = os.environ.get("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Render health check server listening on port %d", port)
    except Exception as e:
        logger.error("Failed to start Render health server on port %s: %s", port_str, e)


def conversation_key(update: Update) -> str:
    # Separate each user's conversation, including inside group chats.
    return f"{update.effective_chat.id}:{update.effective_user.id}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Hello! I'm Elena AI, created by Elena.\n\n"
        "Send me a message in any language and I'll do my best to help.\n\n"
        "Commands:\n"
        "/settings - choose a Gemini model\n"
        "/new - start a new conversation\n"
        "/clear - clear conversation history\n"
        "/help - show help"
    )
    await update.effective_message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = conversation_key(update)
    current = await asyncio.to_thread(get_model, key) or DEFAULT_MODEL
    rows = []
    for model_id, info in MODELS.items():
        label = f"{'✓ ' if model_id == current else ''}{info['name']}"
        rows.append([InlineKeyboardButton(label, callback_data=f"model:{model_id}")])
    await update.effective_message.reply_text(
        f"⚙️ Choose a Gemini model. Current: {current}",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def safe_edit_message_text(query, text: str, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.warning("edit_message_text failed: %s", e)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    key = f"{query.message.chat_id}:{query.from_user.id}"

    if data.startswith("model:"):
        model_id = data.split(":", 1)[1]
        if model_id not in MODELS:
            await safe_edit_message_text(query, "That model is not configured.")
            return
        await asyncio.to_thread(set_model, key, model_id)
        await safe_edit_message_text(query, f"✅ Model changed to {MODELS[model_id]['name']}.")


async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = conversation_key(update)
    await asyncio.to_thread(clear_history, key)
    await update.effective_message.reply_text("🆕 New conversation started. What would you like to talk about?")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = conversation_key(update)
    await asyncio.to_thread(clear_history, key)
    await update.effective_message.reply_text("🧹 Your conversation history has been cleared.")


def should_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    message = update.effective_message
    if chat.type == "private":
        return True
    bot_username = context.bot.username
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True
    return bool(bot_username and f"@{bot_username.lower()}" in (message.text or "").lower())


async def send_long_message(message, text: str):
    # Telegram message text limit is 4096 characters.
    text = text or "I couldn't generate a text response. Please try again."
    for start_index in range(0, len(text), 4000):
        await message.reply_text(text[start_index:start_index + 4000])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not should_reply_in_group(update, context):
        return
    message = update.effective_message
    user_text = message.text or ""
    if update.effective_chat.type != "private":
        bot_username = context.bot.username
        if bot_username:
            user_text = user_text.replace(f"@{bot_username}", "").strip()

    key = conversation_key(update)
    model = (await asyncio.to_thread(get_model, key)) or DEFAULT_MODEL
    history = await asyncio.to_thread(get_history, key, MAX_HISTORY)

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    try:
        answer = await ask_gemini(model, history, user_text)
        await asyncio.to_thread(add_message, key, "user", user_text)
        await asyncio.to_thread(add_message, key, "model", answer)
        await send_long_message(message, answer)
    except Exception:
        logger.exception("Gemini text request failed")
        await message.reply_text(
            "⚠️ I couldn't reach Gemini right now. Check the API key, model access, "
            "internet connection and API quota, then try again."
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not should_reply_in_group(update, context):
        return
    message = update.effective_message
    key = conversation_key(update)
    model = (await asyncio.to_thread(get_model, key)) or DEFAULT_MODEL
    history = await asyncio.to_thread(get_history, key, MAX_HISTORY)
    caption = message.caption or "Describe this image and answer helpfully."
    try:
        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await telegram_file.download_as_bytearray())
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        answer = await ask_gemini_with_media(
            model, history, caption, image_bytes, "image/jpeg"
        )
        await asyncio.to_thread(add_message, key, "user", f"[Image] {caption}")
        await asyncio.to_thread(add_message, key, "model", answer)
        await send_long_message(message, answer)
    except Exception:
        logger.exception("Image request failed")
        await message.reply_text("⚠️ I couldn't analyze that image. Please try again.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not should_reply_in_group(update, context):
        return
    message = update.effective_message
    key = conversation_key(update)
    model = (await asyncio.to_thread(get_model, key)) or DEFAULT_MODEL
    history = await asyncio.to_thread(get_history, key, MAX_HISTORY)
    try:
        voice = message.voice or message.audio
        telegram_file = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
        mime_type = "audio/ogg" if message.voice else (message.audio.mime_type or "audio/mpeg")
        prompt = (
            "Listen to this audio. Understand the spoken language, transcribe it "
            "internally, and respond helpfully in the same language. If it is a "
            "question, answer it. Do not only return a transcription unless requested."
        )
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        answer = await ask_gemini_with_media(model, history, prompt, audio_bytes, mime_type)
        await asyncio.to_thread(add_message, key, "user", "[Voice message]")
        await asyncio.to_thread(add_message, key, "model", answer)
        await send_long_message(message, answer)
    except Exception:
        logger.exception("Voice request failed")
        await message.reply_text("⚠️ I couldn't process that voice message. Please try again.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled error: %s", context.error)


async def post_init(application: Application):
    commands = [
        BotCommand("start", "Start Elena AI & show menu"),
        BotCommand("settings", "Choose Gemini AI model"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("clear", "Clear conversation history"),
        BotCommand("help", "Help & instructions"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram [/] menu.")
    except Exception as e:
        logger.warning("Failed to register bot commands with Telegram: %s", e)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Set it in your .env file.")
    init_db()
    start_health_server()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("new", new_conversation))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_error_handler(error_handler)

    logger.info("Elena AI is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
