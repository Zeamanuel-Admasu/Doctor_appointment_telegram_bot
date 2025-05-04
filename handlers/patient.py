from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from services.db import doctor_availability
import datetime

# Conversation states
NAME, AGE, SEX, REASON, PHONE, HOSPITAL = range(6)
SELECT_DAY, SELECT_SESSION = range(101, 103)
CONFIRM_CANCEL = 200

HOSPITALS = ["Abet Hospital", "Ethio Tebib Hospital", "Girum Hospital"]
SEX_OPTIONS = [["Male", "Female", "Other"]]


# -------------------- BOOKING FLOW --------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.effective_user.id == int(context.bot_data.get("doctor_id", 0)):
        await update.message.reply_text("Welcome, Doctor. Use /schedule to set your availability.")
        return ConversationHandler.END
    await update.message.reply_text("Welcome! Let's book your appointment.\nWhat is your full name?")
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("How old are you?")
    return AGE


async def collect_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text
    await update.message.reply_text("What is your sex?", reply_markup=ReplyKeyboardMarkup(SEX_OPTIONS, one_time_keyboard=True))
    return SEX


async def collect_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sex"] = update.message.text
    await update.message.reply_text("Briefly describe the reason for your consultation:")
    return REASON


async def collect_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reason"] = update.message.text
    await update.message.reply_text("Enter your phone number:")
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    await update.message.reply_text(
        "Choose your preferred hospital:",
        reply_markup=ReplyKeyboardMarkup([[h] for h in HOSPITALS], one_time_keyboard=True)
    )
    return HOSPITAL


async def collect_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_hospital = update.message.text
    context.user_data["hospital"] = selected_hospital
    today = datetime.date.today()

    available_days = []
    day_options = []

    for offset in range(7):
        date = today + datetime.timedelta(days=offset)
        schedule = doctor_availability.find_one({"hospital": selected_hospital, "date": str(date)})

        if schedule:
            sessions = []
            for session_name, session in schedule.get("sessions", {}).items():
                if any(slot["available"] for slot in session["slots"]):
                    sessions.append(session_name)
            if sessions:
                available_days.append((date, sessions))
                day_name = date.strftime("%A")  # e.g., Monday
                formatted = f"{day_name} ({date.strftime('%Y-%m-%d')})"
                day_options.append([formatted])

    if not available_days:
        await update.message.reply_text(
            "❌ No available slots for this hospital this week.\nPlease choose another hospital:",
            reply_markup=ReplyKeyboardMarkup([[h] for h in HOSPITALS], one_time_keyboard=True)
        )
        return HOSPITAL  # Stay in the same step

    context.user_data["available_days"] = available_days
    await update.message.reply_text("📅 Available days this week:\nChoose a date:",
                                    reply_markup=ReplyKeyboardMarkup(day_options, one_time_keyboard=True))
    return SELECT_DAY


async def select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extract actual date from message, e.g., from "Monday (2025-05-05)" → "2025-05-05"
    raw_text = update.message.text
    try:
        chosen_date = raw_text.split("(")[-1].strip(")")
    except Exception:
        await update.message.reply_text("❌ Please select a valid date from the list.")
        return SELECT_DAY

    context.user_data["chosen_date"] = chosen_date

    for date, sessions in context.user_data.get("available_days", []):
        if str(date) == chosen_date:
            context.user_data["available_sessions"] = sessions
            break
    else:
        await update.message.reply_text("❌ No sessions found for that day. Please try again.")
        return SELECT_DAY

    session_buttons = [[s.capitalize()] for s in context.user_data["available_sessions"]]
    await update.message.reply_text(
        "🕓 Which session would you prefer?",
        reply_markup=ReplyKeyboardMarkup(session_buttons, one_time_keyboard=True)
    )
    return SELECT_SESSION



async def select_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_choice = update.message.text.lower()
    hospital = context.user_data["hospital"]
    chosen_date = context.user_data["chosen_date"]
    user_id = update.effective_user.id

    # Prevent duplicate appointment in same week
    selected_date = datetime.datetime.strptime(chosen_date, "%Y-%m-%d").date()
    week_start = selected_date - datetime.timedelta(days=selected_date.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    existing = doctor_availability.find({
        "date": {"$gte": str(week_start), "$lte": str(week_end)}
    })

    for doc in existing:
        for session in doc.get("sessions", {}).values():
            for slot in session["slots"]:
                if slot.get("patientId") == user_id:
                    await update.message.reply_text("⚠️ You already have an appointment this week. Please cancel it first or wait until next week.")
                    return ConversationHandler.END

    schedule = doctor_availability.find_one({"hospital": hospital, "date": chosen_date})
    session = schedule["sessions"][session_choice]

    for slot in session["slots"]:
        if slot["available"]:
            slot["available"] = False
            slot["patientId"] = user_id
            slot["patientInfo"] = {
                "name": context.user_data["name"],
                "age": context.user_data["age"],
                "sex": context.user_data["sex"],
                "reason": context.user_data["reason"],
                "phone": context.user_data["phone"],
            }

            doctor_availability.update_one(
                {"_id": schedule["_id"]},
                {"$set": {f"sessions.{session_choice}.slots": session["slots"]}}
            )

            await update.message.reply_text(
                f"✅ Appointment booked!\n🏥 {hospital}\n📅 {chosen_date}\n🕓 {slot['time']}"
            )
            return ConversationHandler.END

    await update.message.reply_text("⚠️ Sorry, that session just filled up.")
    return ConversationHandler.END

async def my_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.date.today()
    appointments = []

    for doc in doctor_availability.find({"date": {"$gte": str(today)}}).sort("date"):
        for session_name, session in doc.get("sessions", {}).items():
            for slot in session["slots"]:
                if slot.get("patientId") == user_id:
                    appointments.append({
                        "schedule_id": doc["_id"],
                        "session": session_name,
                        "slot_time": slot["time"],
                        "hospital": doc["hospital"],
                        "date": doc["date"]
                    })

    if not appointments:
        await update.message.reply_text("🔎 You don’t have any upcoming appointments.")
        return ConversationHandler.END

    context.user_data["appointments"] = appointments
    buttons = [[f"{i+1}. {appt['hospital']} - {appt['date']} - {appt['slot_time']} ({appt['session']})"]
               for i, appt in enumerate(appointments)]
    await update.message.reply_text("📋 Your appointments:\nChoose one to cancel:", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True))
    return CONFIRM_CANCEL


async def confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        idx = int(update.message.text.split(".")[0]) - 1
        appt = context.user_data["appointments"][idx]
    except:
        await update.message.reply_text("❌ Invalid selection.")
        return ConversationHandler.END

    schedule = doctor_availability.find_one({"_id": appt["schedule_id"]})
    if schedule:
        slots = schedule["sessions"][appt["session"]]["slots"]
        for slot in slots:
            if slot["time"] == appt["slot_time"] and slot.get("patientId") == update.effective_user.id:
                slot["available"] = True
                slot["patientId"] = None
                slot["patientInfo"] = None

        doctor_availability.update_one(
            {"_id": schedule["_id"]},
            {"$set": {f"sessions.{appt['session']}.slots": slots}}
        )

    await update.message.reply_text("✅ Appointment cancelled.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# -------------------- REGISTER --------------------

def register_patient_handler(app, doctor_id: int):
    app.bot_data["doctor_id"] = doctor_id

    booking_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_age)],
            SEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_sex)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_reason)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            HOSPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_hospital)],
            SELECT_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_day)],
            SELECT_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_session)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_handler)
        ],
    )

    cancel_conv = ConversationHandler(
        entry_points=[CommandHandler("myappointment", my_appointment)],
        states={
            CONFIRM_CANCEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_cancel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(booking_conv)
    app.add_handler(cancel_conv)
