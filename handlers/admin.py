from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import datetime
from services.db import doctor_availability
import os

DOCTOR_ID = int(os.getenv("DOCTOR_TELEGRAM_ID"))

# States
HOSPITAL, DAY, SESSION, CONFIRM_OVERWRITE, VIEW_DAY = range(5)

HOSPITALS = ["Abet Hospital", "Ethio Tebib Hospital", "Girum Hospital"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SESSIONS = ["Morning", "Afternoon", "Both"]


def generate_slots(start_time, end_time, count=10):
    duration = int((end_time - start_time).total_seconds() // 60 // count)
    return [
        {
            "time": (start_time + datetime.timedelta(minutes=duration * i)).strftime("%H:%M"),
            "available": True,
            "patientId": None
        } for i in range(count)
    ]


# ==================== Schedule Flow ====================

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DOCTOR_ID:
        await update.message.reply_text("You are not authorized.")
        return ConversationHandler.END

    await update.message.reply_text("Choose a hospital:", reply_markup=ReplyKeyboardMarkup([[h] for h in HOSPITALS], one_time_keyboard=True))
    return HOSPITAL


async def select_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["hospital"] = update.message.text
    await update.message.reply_text("Select a day:", reply_markup=ReplyKeyboardMarkup([[d] for d in DAYS], one_time_keyboard=True))
    return DAY


async def select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = update.message.text
    context.user_data["day"] = day

    weekday_to_date = {
        name: (datetime.datetime.now() + datetime.timedelta(days=(i - datetime.datetime.now().weekday()) % 7)).date()
        for i, name in enumerate(DAYS)
    }
    selected_date = weekday_to_date[day]
    context.user_data["selected_date"] = selected_date

    existing = doctor_availability.find_one({"date": str(selected_date)})
    if existing:
        context.user_data["existing_schedule"] = existing
        await update.message.reply_text(
            f"⚠️ Already scheduled for {existing['hospital']} on {selected_date}.\n"
            f"Overwrite with '{context.user_data['hospital']}'?",
            reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True)
        )
        return CONFIRM_OVERWRITE

    await update.message.reply_text("Select session:", reply_markup=ReplyKeyboardMarkup([[s] for s in SESSIONS], one_time_keyboard=True))
    return SESSION


async def confirm_overwrite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() != "yes":
        await update.message.reply_text("❌ Schedule unchanged.")
        return ConversationHandler.END

    existing = context.user_data["existing_schedule"]
    selected_date = context.user_data["selected_date"]

    for session in ["morning", "afternoon"]:
        for slot in existing.get("sessions", {}).get(session, {}).get("slots", []):
            patient_id = slot.get("patientId")
            if patient_id:
                try:
                    await context.bot.send_message(
                        chat_id=patient_id,
                        text=f"⚠️ Your appointment on {selected_date} at {existing['hospital']} was cancelled. Please rebook."
                    )
                except Exception as e:
                    print(f"Notification failed: {e}")

    doctor_availability.delete_one({"_id": existing["_id"]})
    await update.message.reply_text("🗑️ Old schedule deleted. Now select session:",
                                    reply_markup=ReplyKeyboardMarkup([[s] for s in SESSIONS], one_time_keyboard=True))
    return SESSION


async def select_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hospital = context.user_data["hospital"]
    selected_date = context.user_data["selected_date"]
    session_choice = update.message.text
    day = context.user_data["day"]

    session_data = {}

    if session_choice in ["Morning", "Both"]:
        start = datetime.datetime.combine(selected_date, datetime.time(8, 30))
        end = datetime.datetime.combine(selected_date, datetime.time(12, 0))
        session_data["morning"] = {
            "startTime": "08:30",
            "endTime": "12:00",
            "slots": generate_slots(start, end, 10)
        }

    if session_choice in ["Afternoon", "Both"]:
        start = datetime.datetime.combine(selected_date, datetime.time(14, 0))
        end = datetime.datetime.combine(selected_date, datetime.time(17, 0))
        session_data["afternoon"] = {
            "startTime": "14:00",
            "endTime": "17:00",
            "slots": generate_slots(start, end, 10)
        }

    doctor_availability.insert_one({
        "hospital": hospital,
        "date": str(selected_date),
        "sessions": session_data
    })

    await update.message.reply_text(f"✅ Schedule set for {hospital} on {day} ({selected_date}).")
    return ConversationHandler.END


# ==================== View Patients Flow ====================

async def view_patients_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DOCTOR_ID:
        await update.message.reply_text("Not authorized.")
        return

    await update.message.reply_text("📅 Choose a day to view patients:", reply_markup=ReplyKeyboardMarkup([[d] for d in DAYS], one_time_keyboard=True))
    return VIEW_DAY


async def view_patients_by_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = update.message.text
    try:
        i = DAYS.index(day)
    except ValueError:
        await update.message.reply_text("Invalid day. Please select from the list.")
        return VIEW_DAY

    selected_date = (datetime.datetime.now() + datetime.timedelta(days=(i - datetime.datetime.now().weekday()) % 7)).date()

    schedule = doctor_availability.find_one({"date": str(selected_date)})
    if not schedule:
        await update.message.reply_text("No schedule found for that date.")
        return ConversationHandler.END

    response = f"📅 Appointments for {selected_date} at {schedule['hospital']}:\n"
    found = False
    for session_name, session in schedule.get("sessions", {}).items():
        response += f"\n🕓 {session_name.capitalize()} Session:\n"
        for slot in session["slots"]:
            if slot.get("patientId"):
                info = slot.get("patientInfo", {})
                response += f"• {slot['time']}: {info.get('name')} ({info.get('phone')})\n"
                found = True

    if not found:
        response += "No patients booked."
    await update.message.reply_text(response)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ==================== Register Handlers ====================

def register_schedule_handler(app):
    schedule_conv = ConversationHandler(
        entry_points=[CommandHandler("schedule", schedule_handler)],
        states={
            HOSPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_hospital)],
            DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_day)],
            CONFIRM_OVERWRITE: [MessageHandler(filters.Regex("^(Yes|No)$"), confirm_overwrite)],
            SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_session)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    view_conv = ConversationHandler(
        entry_points=[CommandHandler("viewpatients", view_patients_handler)],
        states={
            VIEW_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_patients_by_day)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(schedule_conv)
    app.add_handler(view_conv)
