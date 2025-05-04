# main.py
import os
import datetime
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder
from handlers.admin import register_schedule_handler
from handlers.patient import register_patient_handler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DOCTOR_ID = int(os.getenv("DOCTOR_TELEGRAM_ID"))
PORT = int(os.getenv("PORT", 8000))

app = FastAPI()
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

register_schedule_handler(telegram_app)
register_patient_handler(telegram_app, DOCTOR_ID)

async def set_bot_commands():
    await telegram_app.bot.set_my_commands(
        [
            BotCommand("schedule", "Set your weekly availability"),
            BotCommand("viewpatients", "View patients by date"),
        ],
        scope={"type": "chat", "chat_id": DOCTOR_ID},
    )
    await telegram_app.bot.set_my_commands(
        [
            BotCommand("start", "Start appointment booking"),
            BotCommand("myappointment", "View or cancel appointment"),
        ]
    )

@app.post(f"/webhook/{BOT_TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

def ping_self():
    print(f"[{datetime.datetime.now()}] ⏰ Keep-alive ping running...")

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await set_bot_commands()
    await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
    await telegram_app.start()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(ping_self, 'interval', minutes=15)
    scheduler.start()
