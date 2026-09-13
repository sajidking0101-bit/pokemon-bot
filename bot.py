import logging
import os
from datetime import datetime, timedelta

import aiosqlite
from flask import Flask
from threading import Thread

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_ID
from database import (
    init_db,
    add_user,
    is_blocked,
    set_blocked,
    add_admin,
    is_admin,
    set_setting,
    get_setting,
)

# =========================================================
# CONFIG
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

PORT = int(os.environ.get("PORT", "10000"))

# Conversation states
WAITING_FILE = 1
WAITING_FILE_NAME = 2
WAITING_FILE_DESCRIPTION = 3
WAITING_BLOCK_ID = 4
WAITING_UNBLOCK_ID = 5


# =========================================================
# FLASK
# =========================================================

@app.route("/")
def home():
    return "Pokemon File Sharing Bot is Running!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    app.run(
        host="0.0.0.0",
        port=PORT,
        use_reloader=False,
    )


# =========================================================
# DATABASE HELPERS
# =========================================================

async def get_active_files():
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute("""
            SELECT id, file_id, file_type, name, description
            FROM files
            WHERE is_active = 1
            ORDER BY id DESC
        """)
        return await cursor.fetchall()


async def get_file(file_db_id):
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute("""
            SELECT id, file_id, file_type, name, description, is_active
            FROM files
            WHERE id = ?
        """, (file_db_id,))
        return await cursor.fetchone()


async def add_file_to_db(
    file_id,
    file_type,
    name,
    description,
):
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute("""
            INSERT INTO files
            (file_id, file_type, name, description, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (
            file_id,
            file_type,
            name,
            description,
            datetime.utcnow().isoformat(),
        ))

        await db.commit()
        return cursor.lastrowid


async def delete_file_from_db(file_db_id):
    async with aiosqlite.connect("pokemon_bot.db") as db:
        await db.execute("""
            UPDATE files
            SET is_active = 0
            WHERE id = ?
        """, (file_db_id,))
        await db.commit()


async def get_users_count():
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users"
        )
        row = await cursor.fetchone()
        return row[0]


async def get_files_count():
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM files WHERE is_active = 1"
        )
        row = await cursor.fetchone()
        return row[0]


async def get_blocked_count():
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE is_blocked = 1"
        )
        row = await cursor.fetchone()
        return row[0]


async def get_premium_count():
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE is_premium = 1"
        )
        row = await cursor.fetchone()
        return row[0]


async def set_premium(user_id, expiry):
    async with aiosqlite.connect("pokemon_bot.db") as db:
        await db.execute("""
            UPDATE users
            SET is_premium = 1,
                premium_expiry = ?
            WHERE user_id = ?
        """, (
            expiry.isoformat(),
            user_id,
        ))
        await db.commit()


async def check_premium(user_id):
    async with aiosqlite.connect("pokemon_bot.db") as db:
        cursor = await db.execute("""
            SELECT is_premium, premium_expiry
            FROM users
            WHERE user_id = ?
        """, (user_id,))

        row = await cursor.fetchone()

        if not row:
            return False

        is_premium_user, expiry_text = row

        if not is_premium_user or not expiry_text:
            return False

        try:
            expiry = datetime.fromisoformat(expiry_text)

            if datetime.utcnow() >= expiry:
                await db.execute("""
                    UPDATE users
                    SET is_premium = 0
                    WHERE user_id = ?
                """, (user_id,))
                await db.commit()
                return False

            return True

        except Exception:
            return False


# =========================================================
# KEYBOARDS
# =========================================================

def user_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📂 Browse Files",
                callback_data="files"
            )
        ],
        [
            InlineKeyboardButton(
                "💎 Premium Membership",
                callback_data="membership"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ About",
                callback_data="about"
            )
        ],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users"
            ),
            InlineKeyboardButton(
                "📁 Files",
                callback_data="admin_files"
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 Channels",
                callback_data="admin_channels"
            ),
            InlineKeyboardButton(
                "⚙️ Settings",
                callback_data="admin_settings"
            ),
        ],
        [
            InlineKeyboardButton(
                "💎 Membership",
                callback_data="admin_membership"
            ),
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            ),
        ],
        [
            InlineKeyboardButton(
                "🚫 Block User",
                callback_data="admin_block"
            ),
            InlineKeyboardButton(
                "✅ Unblock User",
                callback_data="admin_unblock"
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ Close",
                callback_data="close"
            ),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "↩️ Back",
                callback_data="admin_panel"
            )
        ]
    ])


def files_keyboard(files):
    buttons = []

    for row in files:
        file_db_id = row[0]
        name = row[3] or f"File #{file_db_id}"

        buttons.append([
            InlineKeyboardButton(
                f"🔒 {name}",
                callback_data=f"open_file:{file_db_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "↩️ Back",
            callback_data="user_home"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# =========================================================
# ADMIN CHECK
# =========================================================

async def is_user_admin(user_id):
    return (
        user_id == ADMIN_ID
        or await is_admin(user_id)
    )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await add_user(
        user.id,
        user.username,
        user.first_name,
    )

    if await is_blocked(user.id):
        await update.message.reply_text(
            "🚫 <b>ACCESS BLOCKED</b>\n\n"
            "You are blocked from using this bot.",
            parse_mode="HTML",
        )
        return

    text = (
        "🔥 <b>WELCOME TO POKEMON FILE SHARING</b> 🔥\n\n"
        "⚡ <b>Fast & Easy File Access</b>\n"
        "📂 <b>Premium Files</b>\n"
        "🔐 <b>Secure File System</b>\n"
        "💎 <b>Premium Membership</b>\n\n"
        "✨ Choose an option below ✨"
    )

    await update.message.reply_text(
        text,
        reply_markup=user_keyboard(),
        parse_mode="HTML",
    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_admin(user.id):
        await update.message.reply_text(
            "⛔ <b>ADMIN ACCESS DENIED</b>",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        "👑 <b>POKEMON FILE SHARING</b>\n"
        "🔥 <b>ADMIN PANEL</b>\n\n"
        "⚙️ Select what you want to manage:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


# =========================================================
# ADD FILE CONVERSATION
# =========================================================

async def add_file_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_admin(user.id):
        await update.message.reply_text(
            "⛔ Admin access denied."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📤 <b>ADD NEW FILE</b>\n\n"
        "Send the file now.\n\n"
        "Supported:\n"
        "🎬 Video\n"
        "📄 Document\n"
        "🎵 Audio\n"
        "🖼️ Photo",
        parse_mode="HTML",
    )

    return WAITING_FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_admin(user.id):
        return ConversationHandler.END

    message = update.message

    file_id = None
    file_type = None

    if message.document:
        file_id = message.document.file_id
        file_type = "document"

    elif message.video:
        file_id = message.video.file_id
        file_type = "video"

    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"

    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"

    else:
        await message.reply_text(
            "❌ Please send a video, document, audio or photo."
        )
        return WAITING_FILE

    context.user_data["new_file_id"] = file_id
    context.user_data["new_file_type"] = file_type

    await message.reply_text(
        "✅ <b>FILE RECEIVED</b>\n\n"
        "Now send the <b>file name</b>.\n\n"
        "Example:\n"
        "<code>Pokemon Episode 01</code>",
        parse_mode="HTML",
    )

    return WAITING_FILE_NAME


async def receive_file_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "❌ File name cannot be empty."
        )
        return WAITING_FILE_NAME

    context.user_data["new_file_name"] = name

    await update.message.reply_text(
        "📝 Now send a short <b>description</b>.\n\n"
        "Example:\n"
        "<code>Pokemon Episode 01 HD</code>\n\n"
        "If you don't want a description, send:\n"
        "<code>none</code>",
        parse_mode="HTML",
    )

    return WAITING_FILE_DESCRIPTION


async def receive_file_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    description = update.message.text.strip()

    if description.lower() == "none":
        description = ""

    file_id = context.user_data.get("new_file_id")
    file_type = context.user_data.get("new_file_type")
    name = context.user_data.get("new_file_name")

    if not file_id:
        await update.message.reply_text(
            "❌ File session expired. Start again."
        )
        return ConversationHandler.END

    db_id = await add_file_to_db(
        file_id,
        file_type,
        name,
        description,
    )

    context.user_data.clear()

    await update.message.reply_text(
        "🎉 <b>FILE ADDED SUCCESSFULLY!</b>\n\n"
        f"🆔 File ID: <code>{db_id}</code>\n"
        f"📁 Name: <b>{name}</b>\n"
        f"📦 Type: <b>{file_type}</b>\n"
        f"📝 Description: {description or 'None'}\n\n"
        "🔒 File is now available in the file center.",
        parse_mode="HTML",
    )

    return ConversationHandler.END


# =========================================================
# BLOCK / UNBLOCK
# =========================================================

async def block_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_admin(user.id):
        return ConversationHandler.END

    await update.message.reply_text(
        "🚫 <b>BLOCK USER</b>\n\n"
        "Send the user's numeric Telegram ID.",
        parse_mode="HTML",
    )

    return WAITING_BLOCK_ID


async def block_user_receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID."
        )
        return WAITING_BLOCK_ID

    await set_blocked(target_id, True)

    await update.message.reply_text(
        "🚫 <b>USER BLOCKED</b>\n\n"
        f"User ID: <code>{target_id}</code>",
        parse_mode="HTML",
    )

    return ConversationHandler.END


async def unblock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_admin(user.id):
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ <b>UNBLOCK USER</b>\n\n"
        "Send the user's numeric Telegram ID.",
        parse_mode="HTML",
    )

    return WAITING_UNBLOCK_ID


async def unblock_user_receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID."
        )
        return WAITING_UNBLOCK_ID

    await set_blocked(target_id, False)

    await update.message.reply_text(
        "✅ <b>USER UNBLOCKED</b>\n\n"
        f"User ID: <code>{target_id}</code>",
        parse_mode="HTML",
    )

    return ConversationHandler.END


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if await is_blocked(user_id):
        await query.edit_message_text(
            "🚫 <b>ACCESS BLOCKED</b>",
            parse_mode="HTML",
        )
        return

    # =====================================================
    # USER HOME
    # =====================================================

    if data == "user_home":
        await query.edit_message_text(
            "🔥 <b>POKEMON FILE SHARING</b> 🔥\n\n"
            "✨ Choose an option:",
            reply_markup=user_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # FILES
    # =====================================================

    if data == "files":
        files = await get_active_files()

        if not files:
            await query.edit_message_text(
                "📂 <b>FILE CENTER</b>\n\n"
                "😔 No files are available right now.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "↩️ Back",
                            callback_data="user_home"
                        )
                    ]
                ]),
                parse_mode="HTML",
            )
            return

        await query.edit_message_text(
            "📂 <b>FILE CENTER</b>\n\n"
            "🔒 Select a file:",
            reply_markup=files_keyboard(files),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # OPEN FILE
    # =====================================================

    if data.startswith("open_file:"):
        try:
            file_db_id = int(data.split(":")[1])
        except Exception:
            await query.answer(
                "Invalid file.",
                show_alert=True
            )
            return

        row = await get_file(file_db_id)

        if not row or not row[5]:
            await query.answer(
                "File not available.",
                show_alert=True
            )
            return

        file_id = row[1]
        file_type = row[2]
        name = row[3] or "File"
        description = row[4] or ""

        # Current unlock system:
        # Admin can later connect ad unlock here.
        # Premium users can access directly.
        premium = await check_premium(user_id)

        if not premium:
            await query.edit_message_text(
                "🔒 <b>FILE LOCKED</b>\n\n"
                f"📁 <b>{name}</b>\n\n"
                f"📝 {description or 'Premium file'}\n\n"
                "🔐 This file is locked.\n\n"
                "💎 Get Premium Membership to access files.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "💎 Get Premium",
                            callback_data="membership"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "↩️ Back",
                            callback_data="files"
                        )
                    ],
                ]),
                parse_mode="HTML",
            )
            return

        # Premium user receives file
        await query.message.reply_text(
            f"📦 <b>{name}</b>\n\n"
            f"📝 {description}",
            parse_mode="HTML",
        )

        if file_type == "video":
            await query.message.reply_video(file_id)

        elif file_type == "document":
            await query.message.reply_document(file_id)

        elif file_type == "audio":
            await query.message.reply_audio(file_id)

        elif file_type == "photo":
            await query.message.reply_photo(file_id)

        return

    # =====================================================
    # MEMBERSHIP
    # =====================================================

    if data == "membership":
        stars = await get_setting(
            "membership_stars",
            "100"
        )

        enabled = await get_setting(
            "membership_enabled",
            "1"
        )

        if enabled != "1":
            await query.edit_message_text(
                "💎 <b>PREMIUM MEMBERSHIP</b>\n\n"
                "Currently unavailable.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "↩️ Back",
                            callback_data="user_home"
                        )
                    ]
                ]),
                parse_mode="HTML",
            )
            return

        await query.edit_message_text(
            "💎 <b>PREMIUM MEMBERSHIP</b>\n\n"
            "⭐ Duration: <b>30 Days</b>\n"
            f"💰 Price: <b>{stars} Telegram Stars</b>\n\n"
            "✨ Premium members can access locked files.\n\n"
            "👇 Tap below to continue.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⭐ Buy Membership",
                        callback_data="buy_membership"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "↩️ Back",
                        callback_data="user_home"
                    )
                ],
            ]),
            parse_mode="HTML",
        )
        return

    if data == "buy_membership":
        stars = int(
            await get_setting(
                "membership_stars",
                "100"
            )
        )

        await query.message.reply_invoice(
            title="💎 Pokemon Premium",
            description="30 Days Premium Membership",
            payload=f"membership_30_{user_id}",
            currency="XTR",
            prices=[
                LabeledPrice(
                    "30 Days Premium",
                    stars
                )
            ],
        )
        return

    # =====================================================
    # ABOUT
    # =====================================================

    if data == "about":
        await query.edit_message_text(
            "🔥 <b>POKEMON FILE SHARING</b>\n\n"
            "⚡ Fast file access\n"
            "📂 Organized files\n"
            "🔐 Secure system\n"
            "💎 Premium membership\n"
            "⭐ Telegram Stars payment\n\n"
            "❤️ Enjoy!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "↩️ Back",
                        callback_data="user_home"
                    )
                ]
            ]),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN SECURITY
    # =====================================================

    if data.startswith("admin_"):
        if not await is_user_admin(user_id):
            await query.edit_message_text(
                "⛔ Admin access denied."
            )
            return

    # =====================================================
    # ADMIN PANEL
    # =====================================================

    if data == "admin_panel":
        await query.edit_message_text(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "⚙️ Select a management section:",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":
        users = await get_users_count()
        blocked = await get_blocked_count()
        premium = await get_premium_count()

        await query.edit_message_text(
            "👥 <b>USER MANAGEMENT</b>\n\n"
            f"👤 Total Users: <b>{users}</b>\n"
            f"🚫 Blocked: <b>{blocked}</b>\n"
            f"💎 Premium: <b>{premium}</b>\n\n"
            "Use the Block/Unblock buttons from the admin panel.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN FILES
    # =====================================================

    if data == "admin_files":
        total = await get_files_count()

        await query.edit_message_text(
            "📁 <b>FILE MANAGEMENT</b>\n\n"
            f"📦 Active Files: <b>{total}</b>\n\n"
            "➕ Add files using the command:\n"
            "<code>/addfile</code>\n\n"
            "🗑️ Delete a file using:\n"
            "<code>/deletefile FILE_ID</code>",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN CHANNELS
    # =====================================================

    if data == "admin_channels":
        await query.edit_message_text(
            "📢 <b>CHANNEL MANAGEMENT</b>\n\n"
            "Channel system is ready for the next integration.\n\n"
            "Join-check can be connected later.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN SETTINGS
    # =====================================================

    if data == "admin_settings":
        membership = await get_setting(
            "membership_enabled",
            "1"
        )

        stars = await get_setting(
            "membership_stars",
            "100"
        )

        await query.edit_message_text(
            "⚙️ <b>BOT SETTINGS</b>\n\n"
            f"💎 Membership: "
            f"<b>{'ON' if membership == '1' else 'OFF'}</b>\n"
            f"⭐ Membership Price: <b>{stars} Stars</b>\n\n"
            "Settings can be changed with admin commands.",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN MEMBERSHIP
    # =====================================================

    if data == "admin_membership":
        enabled = await get_setting(
            "membership_enabled",
            "1"
        )

        stars = await get_setting(
            "membership_stars",
            "100"
        )

        await query.edit_message_text(
            "💎 <b>MEMBERSHIP MANAGEMENT</b>\n\n"
            f"🔘 Status: <b>{'ON' if enabled == '1' else 'OFF'}</b>\n"
            f"⭐ Price: <b>{stars} Stars</b>\n"
            "📅 Duration: <b>30 Days</b>\n\n"
            "Commands:\n"
            "<code>/membership_on</code>\n"
            "<code>/membership_off</code>\n"
            "<code>/setstars 100</code>",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN STATS
    # =====================================================

    if data == "admin_stats":
        users = await get_users_count()
        files = await get_files_count()
        blocked = await get_blocked_count()
        premium = await get_premium_count()

        await query.edit_message_text(
            "📊 <b>BOT STATISTICS</b>\n\n"
            f"👥 Users: <b>{users}</b>\n"
            f"📁 Active Files: <b>{files}</b>\n"
            f"🚫 Blocked Users: <b>{blocked}</b>\n"
            f"💎 Premium Users: <b>{premium}</b>",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
        return
        # =====================================================
    # ADMIN BLOCK
    # =====================================================

    if data == "admin_block":
        await query.message.reply_text(
            "🚫 Use:\n"
            "<code>/block USER_ID</code>",
            parse_mode="HTML",
        )
        return

    # =====================================================
    # ADMIN UNBLOCK
    # =====================================================

    if data == "admin_unblock":
        await query.message.reply_text(
            "✅ Use:\n"
            "<code>/unblock USER_ID</code>",
            parse_mode="HTML",
        )
        return

    # =====================================================
    # CLOSE
    # =====================================================

    if data == "close":
        await query.edit_message_text(
            "❌ <b>Admin panel closed.</b>",
            parse_mode="HTML",
        )


# =========================================================
# DELETE FILE
# =========================================================

async def delete_file_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not await is_user_admin(user.id):
        await update.message.reply_text(
            "⛔ Admin access denied."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/deletefile FILE_ID</code>",
            parse_mode="HTML",
        )
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid file ID."
        )
        return

    await delete_file_from_db(file_id)

    await update.message.reply_text(
        "🗑️ <b>FILE DELETED</b>\n\n"
        f"File ID: <code>{file_id}</code>",
        parse_mode="HTML",
    )


# =========================================================
# BLOCK COMMAND
# =========================================================

async def block_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not await is_user_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/block USER_ID</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID."
        )
        return

    await set_blocked(target_id, True)

    await update.message.reply_text(
        "🚫 <b>User blocked successfully.</b>",
        parse_mode="HTML",
    )


# =========================================================
# UNBLOCK COMMAND
# =========================================================

async def unblock_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not await is_user_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/unblock USER_ID</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID."
        )
        return

    await set_blocked(target_id, False)

    await update.message.reply_text(
        "✅ <b>User unblocked successfully.</b>",
        parse_mode="HTML",
    )


# =========================================================
# MEMBERSHIP SETTINGS
# =========================================================

async def membership_on(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not await is_user_admin(update.effective_user.id):
        return

    await set_setting(
        "membership_enabled",
        "1"
    )

    await update.message.reply_text(
        "💎 Membership is now <b>ON</b>.",
        parse_mode="HTML",
    )


async def membership_off(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not await is_user_admin(update.effective_user.id):
        return

    await set_setting(
        "membership_enabled",
        "0"
    )

    await update.message.reply_text(
        "💎 Membership is now <b>OFF</b>.",
        parse_mode="HTML",
    )


async def set_stars(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not await is_user_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/setstars 100</code>",
            parse_mode="HTML",
        )
        return

    try:
        stars = int(context.args[0])

        if stars <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Enter a valid Stars amount."
        )
        return

    await set_setting(
        "membership_stars",
        str(stars)
    )

    await update.message.reply_text(
        f"⭐ Membership price set to <b>{stars} Stars</b>.",
        parse_mode="HTML",
    )


# =========================================================
# TELEGRAM STARS PAYMENT
# =========================================================

async def precheckout_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.pre_checkout_query

    await query.answer(
        ok=True
    )


async def successful_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    payment = update.message.successful_payment

    user_id = update.effective_user.id

    expiry = datetime.utcnow() + timedelta(days=30)

    await set_premium(
        user_id,
        expiry
        )
        async with aiosqlite.connect("pokemon_bot.db") as db:
        await db.execute("""
            INSERT INTO membership_payments
            (user_id, telegram_payment_id, stars,
             started_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (
            user_id,
            payment.telegram_payment_charge_id,
            payment.total_amount,
            datetime.utcnow().isoformat(),
            expiry.isoformat(),
        ))

        await db.commit()

    await update.message.reply_text(
        "🎉 <b>PAYMENT SUCCESSFUL!</b>\n\n"
        "💎 Your Premium Membership is now active.\n"
        "📅 Duration: <b>30 Days</b>\n\n"
        "🔥 You can now access locked files.",
        parse_mode="HTML",
    )


# =========================================================
# POST INIT
# =========================================================

async def post_init(application: Application):
    await init_db()

    await add_admin(
        ADMIN_ID
    )

    await set_setting(
        "membership_enabled",
        await get_setting(
            "membership_enabled",
            "1"
        )
    )

        await set_setting(
        "membership_stars",
        await get_setting(
            "membership_stars",
            "100"
        )
        )
        
        
        
            
        


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # -------------------------
    # NORMAL COMMANDS
    # -------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin
        )
    )

    application.add_handler(
        CommandHandler(
            "deletefile",
            delete_file_command
        )
    )

    application.add_handler(
        CommandHandler(
            "block",
            block_command
        )
    )

    application.add_handler(
        CommandHandler(
            "unblock",
            unblock_command
        )
    )

    application.add_handler(
        CommandHandler(
            "membership_on",
            membership_on
        )
    )

    application.add_handler(
        CommandHandler(
            "membership_off",
            membership_off
        )
    )

    application.add_handler(
        CommandHandler(
            "setstars",
            set_stars
        )
    )

    # -------------------------
    # ADD FILE CONVERSATION
    # -------------------------

    add_file_conversation = ConversationHandler(
        entry_points=[
            CommandHandler(
                "addfile",
                add_file_start
            )
        ],

        states={
            WAITING_FILE: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.VIDEO
                    | filters.AUDIO
                    | filters.PHOTO,
                    receive_file,
                )
            ],

            WAITING_FILE_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_file_name,
                )
            ],

            WAITING_FILE_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_file_description,
                )
            ],
        },

        fallbacks=[],
    )

    application.add_handler(
        add_file_conversation
    )

    # -------------------------
    # PAYMENT
    # -------------------------

    application.add_handler(
        PreCheckoutQueryHandler(
            precheckout_callback
        )
    )

    application.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_payment,
        )
    )

    # -------------------------
    # BUTTONS
    # -------------------------

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # -------------------------
    # FLASK
    # -------------------------

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    # -------------------------
    # START BOT
    # -------------------------

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
