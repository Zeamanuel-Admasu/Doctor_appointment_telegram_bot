from telegram.ext import ApplicationBuilder
from handlers.admin import register_schedule_handler
from handlers.patient import register_patient_handler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from services.db import doctor_availability  # or wherever your Mongo logic is
import datetime, os
from dotenv import load_dotenv
from flask import Flask, request
import asyncio
from telegram import BotCommand

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://your-app-name.up.railway.app

app = ApplicationBuilder().token(BOT_TOKEN).build()

# Register command handlers
register_schedule_handler(app)
register_patient_handler(app, int(os.getenv("DOCTOR_TELEGRAM_ID")))

# Set commands for different roles
async def set_bot_commands(application):
    doctor_id = int(os.getenv("DOCTOR_TELEGRAM_ID"))
    await application.bot.set_my_commands(
        [
            BotCommand("schedule", "Set your weekly availability"),
            BotCommand("viewpatients", "View patients by date"),
        ],
        scope={"type": "chat", "chat_id": doctor_id},
    )
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start appointment booking"),
            BotCommand("myappointment", "View or cancel appointment"),
        ]
    )

app.post_init = set_bot_commands

# Create Flask app for webhook handler
flask_app = Flask(__name__)

@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    update = app.update_queue.put_nowait
    request_data = request.get_json(force=True)
    update(app._update_queue._application.bot._parser.parse(update=request_data, bot=app.bot))
    return "ok"

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"))
    print("Webhook set. Flask app running...")
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
