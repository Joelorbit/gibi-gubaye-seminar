import logging
import aiosqlite
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# BOT_TOKEN and ADMIN_ID are loaded from environment (.env) below after logger is configured
# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
DB_NAME = "entries.db"

# Load environment variables from .env (if present) and environment
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set. Please create a .env file or set BOT_TOKEN in your environment.")

if ADMIN_ID is None:
    raise RuntimeError("ADMIN_ID environment variable not set. Please create a .env file or set ADMIN_ID in your environment.")

async def init_db():
    """Initialize SQLite database with tables."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                category TEXT,
                text TEXT
            )
        """)
        await db.commit()


async def add_entry(user_id, username, category, text):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO entries (user_id, username, category, text) VALUES (?, ?, ?, ?)",
            (user_id, username, category, text)
        )
        await db.commit()


async def get_entries():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT category, username, text FROM entries")
        rows = await cursor.fetchall()
        return rows


async def get_category_entries(category):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT username, text FROM entries WHERE category = ?",
            (category,)
        )
        return await cursor.fetchall()

# ================== BOT HANDLERS ==================
user_state = {}  # {user_id: selected_category}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🍎 Fruits", callback_data="fruits")],
        [InlineKeyboardButton("🥕 Vegetables", callback_data="vegetables")],
        [InlineKeyboardButton("🥤 Drinks", callback_data="drinks")],
        [InlineKeyboardButton("📦 Others", callback_data="others")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a category:", reply_markup=reply_markup)


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category = query.data
    user_state[query.from_user.id] = category
    await query.edit_message_text(
        text=f"You chose *{category.capitalize()}*.\nNow send me your entry.",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text.strip()

    if user.id not in user_state:
        await update.message.reply_text("Please choose a category first using /start.")
        return

    category = user_state[user.id]
    await add_entry(user.id, user.first_name, category, text)

    await update.message.reply_text(f"✅ Added to *{category.capitalize()}*!", parse_mode="Markdown")

    # Notify admin
    await context.bot.send_message(
        ADMIN_ID,
        f"📬 *New entry in {category.capitalize()}*\n\n{text}\n\nFrom: {user.first_name}",
        parse_mode="Markdown"
    )


async def view_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    entries = await get_entries()
    if not entries:
        await update.message.reply_text("No entries yet.")
        return

    msg = "📊 *Category Entries Overview:*\n\n"
    cats = {"fruits": [], "vegetables": [], "drinks": [], "others": []}
    for category, username, text in entries:
        cats[category].append(f"{username}: {text}")

    for cat, values in cats.items():
        msg += f"*{cat.capitalize()}* ({len(values)} entries):\n"
        if values:
            msg += "\n".join(f"• {v}" for v in values[-5:]) + "\n"
        else:
            msg += "_No entries yet_\n"
        msg += "\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

import asyncio

# ================== MAIN ==================
def main():
    # For Windows: ensure the right event loop policy
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass  # not needed on non-Windows

    async def run_bot():
        await init_db()

        app = ApplicationBuilder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("view", view_entries))
        app.add_handler(CallbackQueryHandler(choose_category))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("🤖 Bot is running...")
        # Important: no asyncio.run() inside — this manages the loop internally
        await app.initialize()
        await app.start()
        await app.updater.start_polling()  # safer for mixed environments

        # Keep running until manually stopped
        await asyncio.Event().wait()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bot())

if __name__ == "__main__":
    main()
