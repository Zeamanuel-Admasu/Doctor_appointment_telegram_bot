from telegram.ext import ApplicationBuilder
from handlers.admin import register_schedule_handler
from handlers.patient import register_patient_handler
from apscheduler.schedulers.background import BackgroundScheduler
from services.db import doctor_availability
from flask import Flask, request
from telegram import BotCommand
import datetime, os, asyncio
from dotenv import load_dotenv
from telegram import Update

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DOCTOR_ID = int(os.getenv("DOCTOR_TELEGRAM_ID"))

# Create Telegram bot application
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Register command handlers
register_schedule_handler(app)
register_patient_handler(app, DOCTOR_ID)

# Set bot commands
async def set_bot_commands(application):
    await application.bot.set_my_commands(
        [
            BotCommand("schedule", "Set your weekly availability"),
            BotCommand("viewpatients", "View patients by date"),
        ],
        scope={"type": "chat", "chat_id": DOCTOR_ID},
    )
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start appointment booking"),
            BotCommand("myappointment", "View or cancel appointment"),
        ]
    )

app.post_init = set_bot_commands

# Flask app for webhook
flask_app = Flask(__name__)

@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    update_data = request.get_json(force=True)
    update = Update.de_json(update_data, app.bot)
    asyncio.get_event_loop().create_task(app.process_update(update))
    return "ok"

# Keep-alive ping every 15 minutes
def ping_self():
    print(f"[{datetime.datetime.now()}] ⏰ Keep-alive ping running...")

scheduler = BackgroundScheduler()
scheduler.add_job(ping_self, 'interval', minutes=15)
scheduler.start()

if __name__ == "__main__":
    # Set webhook on startup
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"))
    print("Webhook set. Flask app running...")

    # Start Flask server
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
