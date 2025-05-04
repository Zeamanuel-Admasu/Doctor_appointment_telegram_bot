from telegram.ext import ApplicationBuilder
from handlers.admin import register_schedule_handler
from handlers.patient import register_patient_handler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from services.db import doctor_availability  # or wherever your Mongo logic is
import datetime, os
from dotenv import load_dotenv

load_dotenv()
app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

# Register handlers
register_schedule_handler(app)
register_patient_handler(app, int(os.getenv("DOCTOR_TELEGRAM_ID")))

# Clean-up function
def remove_old_schedules():
    today = datetime.date.today()
    result = doctor_availability.delete_many({"date": {"$lt": str(today)}})
    print(f"🧹 Deleted {result.deleted_count} old schedules")

# 🧠 Set bot commands and start scheduler after bot initializes
async def post_init(application):
    # Bot commands
    from telegram import BotCommand
    doctor_id = int(os.getenv("DOCTOR_TELEGRAM_ID"))
    await application.bot.set_my_commands(
        [
            BotCommand("schedule", "Set your weekly availability"),
            BotCommand("viewpatients", "View patients by date"),
        ],
        scope={"type": "chat", "chat_id": doctor_id}
    )
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start appointment booking"),
            BotCommand("myappointment", "View or cancel appointment"),
        ]
    )

    # Start scheduler inside event loop
    scheduler = AsyncIOScheduler()
    scheduler.add_job(remove_old_schedules, CronTrigger(hour=0, minute=0))  # every day at midnight
    scheduler.start()
    print("✅ Scheduler started")

# Set post-init
app.post_init = post_init

if __name__ == "__main__":
    print("Bot running...")
    app.run_polling()
