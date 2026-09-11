import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Pokemon Bot!\n\n"
        "📁 Files ke liye /file use karo."
    )


async def file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 File system abhi setup ho raha hai.\n"
        "Admin panel connect hone ke baad yahan files milengi."
    )


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("file", file_command))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
