from telegram import Update
from telegram.ext import ContextTypes

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Process cancelled. You can type /start to begin again.")
