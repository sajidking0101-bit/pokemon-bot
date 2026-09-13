import logging
from flask import Flask
from threading import Thread

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import BOT_TOKEN, ADMIN_ID
from database import (
    init_db,
    add_user,
    is_blocked,
    set_blocked,
    add_admin,
    is_admin,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

app = Flask(__name__)


@app.route("/")
def home():
    return "Pokemon File Sharing Bot is Running!"


@app.route("/health")
def health():
    return "OK"


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("📁 Files", callback_data="admin_files"),
        ],
        [
            InlineKeyboardButton("📢 Channels", callback_data="admin_channels"),
            InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton("💎 Membership", callback_data="admin_membership"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("🚫 Block User", callback_data="admin_block"),
            InlineKeyboardButton("✅ Unblock User", callback_data="admin_unblock"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Back", callback_data="admin_panel")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await add_user(
        user.id,
        user.username,
        user.first_name,
    )

    if await is_blocked(user.id):
        await update.message.reply_text(
            "🚫 You are blocked from using this bot."
        )
        return

    text = (
        "🔥 <b>WELCOME TO POKEMON FILE SHARING</b> 🔥\n\n"
        "⚡ Fast & Easy File Access\n"
        "📂 Your files in one place\n"
        "🔐 Secure file system\n"
        "💎 Premium membership available\n\n"
        "👇 Choose an option below:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 Browse Files", callback_data="files"),
        ],
        [
            InlineKeyboardButton("💎 Premium Membership", callback_data="membership"),
        ],
        [
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
    ])

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id != ADMIN_ID and not await is_admin(user.id):
        await update.message.reply_text("⛔ Admin access denied.")
        return

    await update.message.reply_text(
        "👑 <b>POKEMON FILE SHARING\nADMIN PANEL</b>\n\n"
        "Select what you want to manage:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if await is_blocked(user_id):
        await query.edit_message_text(
            "🚫 You are blocked from using this bot."
        )
        return

    data = query.data

    # =========================
    # USER MENU
    # =========================

    if data == "files":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 Locked Files", callback_data="locked_files")],
            [InlineKeyboardButton("↩️ Back", callback_data="user_home")],
        ])

        await query.edit_message_text(
            "📂 <b>FILE CENTER</b>\n\n"
            "Files will appear here after we connect the file-management system.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if data == "membership":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 1 Month Membership", callback_data="buy_membership")],
            [InlineKeyboardButton("↩️ Back", callback_data="user_home")],
        ])

        await query.edit_message_text(
            "💎 <b>PREMIUM MEMBERSHIP</b>\n\n"
            "1 Month Premium Membership\n\n"
            "⭐ Payment will be made using Telegram Stars.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if data == "about":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Back", callback_data="user_home")]
        ])

        await query.edit_message_text(
            "🔥 <b>POKEMON FILE SHARING</b>\n\n"
            "⚡ Fast\n"
            "🔐 Secure\n"
            "📂 Easy file access\n"
            "💎 Premium features",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if data == "user_home":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 Browse Files", callback_data="files")],
            [InlineKeyboardButton("💎 Premium Membership", callback_data="membership")],
            [InlineKeyboardButton("ℹ️ About", callback_data="about")],
        ])

        await query.edit_message_text(
            "🔥 <b>POKEMON FILE SHARING</b>\n\n"
            "👇 Select an option:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # =========================
    # ADMIN PANEL
    # =========================

    if data.startswith("admin_") and data not in (
        "admin_panel",
    ):
        if user_id != ADMIN_ID and not await is_admin(user_id):
            await query.edit_message_text("⛔ Admin access denied.")
            return

    if data == "admin_panel":
        await query.edit_message_text(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Select a management section:",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_users":
        await query.edit_message_text(
            "👥 <b>USER MANAGEMENT</b>\n\n"
            "User database is connected.\n\n"
            "Next stage will add:\n"
            "• User search\n"
            "• User details\n"
            "• Block / Unblock\n"
            "• Premium status\n"
            "• User ID management",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_files":
        await query.edit_message_text(
            "📁 <b>FILE MANAGEMENT</b>\n\n"
            "Next stage will add:\n"
            "• Add file\n"
            "• Delete file\n"
            "• File ID\n"
            "• File description\n"
            "• File status ON/OFF\n"
            "• File search",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_channels":
        await query.edit_message_text(
            "📢 <b>CHANNEL MANAGEMENT</b>\n\n"
            "Next stage will add:\n"
            "• Add channel\n"
            "• Remove channel\n"
            "• Channel ID\n"
            "• Join-check ON/OFF",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_settings":
        await query.edit_message_text(
            "⚙️ <b>BOT SETTINGS</b>\n\n"
            "Next stage will add ON/OFF controls for every major feature.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_membership":
        await query.edit_message_text(
            "💎 <b>MEMBERSHIP MANAGEMENT</b>\n\n"
            "⭐ Telegram Stars payment\n"
            "📅 30-day membership\n"
            "🔘 Membership ON/OFF\n\n"
            "Payment system will be connected in the next stage.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_stats":
        await query.edit_message_text(
            "📊 <b>BOT STATISTICS</b>\n\n"
            "Statistics system will be connected to the database.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_block":
        await query.edit_message_text(
            "🚫 <b>BLOCK USER</b>\n\n"
            "Next stage: enter a User ID and block that user.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_unblock":
        await query.edit_message_text(
            "✅ <b>UNBLOCK USER</b>\n\n"
            "Next stage: enter a User ID and unblock that user.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "locked_files":
        await query.edit_message_text(
            "🔒 <b>FILES LOCKED</b>\n\n"
            "The file unlock system will be connected later.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "buy_membership":
        await query.edit_message_text(
            "⭐ <b>TELEGRAM STARS MEMBERSHIP</b>\n\n"
            "The 1-month Stars payment system will be connected in the membership stage.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "close":
        await query.edit_message_text("❌ Admin panel closed.")


async def post_init(application: Application):
    await init_db()
    await add_admin(ADMIN_ID)


def run_flask():
    app.run(
        host="0.0.0.0",
        port=10000,
        use_reloader=False,
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing.")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
