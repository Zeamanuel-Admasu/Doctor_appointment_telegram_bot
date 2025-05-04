from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.db import doctor_availability
import datetime
from telegram.ext import ApplicationBuilder
from handlers.admin import register_schedule_handler
from handlers.patient import register_patient_handler
from telegram.ext import CommandHandler
from handlers.common import cancel_handler 
from telegram import BotCommand
import os
from dotenv import load_dotenv

load_dotenv()

app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

# Register handlers
register_schedule_handler(app)
register_patient_handler(app, int(os.getenv("DOCTOR_TELEGRAM_ID")))
def flush_old_schedules():
    today = datetime.date.today()
    result = doctor_availability.delete_many({"date": {"$lt": str(today)}})
    print(f"🧹 Daily cleanup: Deleted {result.deleted_count} outdated schedules.")
# Set bot commands for both roles
async def set_bot_commands(application):
    doctor_id = int(os.getenv("DOCTOR_TELEGRAM_ID"))
    commands_doctor = [
        BotCommand("schedule", "Set your weekly availability"),
        BotCommand("viewpatients", "View patients by date"),
        BotCommand("cancel", "Cancel the current process"),
    ]
    commands_patient = [
        BotCommand("start", "Start appointment booking"),
        BotCommand("myappointment", "View or cancel appointment"),
        BotCommand("cancel", "Cancel the current process"),
    ]
    await application.bot.set_my_commands(commands_doctor, scope={"type": "chat", "chat_id": doctor_id})
    await application.bot.set_my_commands(commands_patient)
    app.add_handler(CommandHandler("cancel", cancel_handler))

# ⛳ RUN
if __name__ == "__main__":
    print("Bot running...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(flush_old_schedules, 'cron', hour=0, minute=0)
    scheduler.start()

    app.post_init = set_bot_commands  # set commands after init
    app.run_polling()  # just this! No asyncio.run or async main
