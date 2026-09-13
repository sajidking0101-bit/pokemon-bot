import aiosqlite
from datetime import datetime

DB_NAME = "pokemon_bot.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_blocked INTEGER DEFAULT 0,
                is_premium INTEGER DEFAULT 0,
                premium_expiry TEXT,
                joined_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                name TEXT,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                channel_name TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS membership_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                telegram_payment_id TEXT,
                stars INTEGER,
                started_at TEXT,
                expires_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        await db.commit()


async def add_user(user_id, username=None, first_name=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users
            (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            datetime.utcnow().isoformat()
        ))
        await db.commit()


async def is_blocked(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT is_blocked FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def set_blocked(user_id, blocked=True):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE users
            SET is_blocked = ?
            WHERE user_id = ?
        """, (1 if blocked else 0, user_id))
        await db.commit()


async def add_admin(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()


async def is_admin(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row is not None


async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (key, str(value)))
        await db.commit()


async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()

        if row:
            return row[0]

        return default
