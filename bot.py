import logging
import sqlite3
import os
from datetime import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO)

DB_PATH = "kassa.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        amount REAL,
        description TEXT,
        created_at TEXT
    )''')
    conn.commit()
    conn.close()

def get_balance(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM operations WHERE chat_id=?", (chat_id,))
    balance = c.fetchone()[0]
    conn.close()
    return balance

def add_operation(chat_id, amount, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO operations (chat_id, amount, description, created_at) VALUES (?,?,?,?)",
              (chat_id, amount, description, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_history(chat_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT amount, description, created_at FROM operations WHERE chat_id=? ORDER BY id DESC LIMIT ?",
              (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def reset_kassa(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM operations WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def format_amount(amount):
    return f"{amount:,.0f}".replace(",", " ")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Бот-касса запущен!*\n\n"
        "Как пользоваться:\n"
        "`+50000 приход наличные` — приход\n"
        "`-30000 выдача Алексей` — расход\n\n"
        "Команды:\n"
        "/касса — текущий остаток\n"
        "/история — последние операции\n"
        "/обнулить — сбросить кассу",
        parse_mode="Markdown"
    )

async def kassa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    balance = get_balance(chat_id)
    emoji = "✅" if balance >= 0 else "⚠️"
    await update.message.reply_text(
        f"{emoji} *Касса:* `{format_amount(balance)} ₽`",
        parse_mode="Markdown"
    )

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = get_history(chat_id)
    if not rows:
        await update.message.reply_text("📋 Операций пока нет.")
        return
    lines = ["📋 *Последние операции:*\n"]
    for amount, desc, dt in rows:
        sign = "➕" if amount > 0 else "➖"
        lines.append(f"{sign} `{format_amount(abs(amount))} ₽` — {desc} _({dt})_")
    balance = get_balance(chat_id)
    lines.append(f"\n💰 *Итого в кассе: {format_amount(balance)} ₽*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reset_kassa(chat_id)
    await update.message.reply_text("🔄 Касса обнулена.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    if text and text[0] in ('+', '-'):
        parts = text.split(None, 1)
        try:
            num_str = parts[0].replace(" ", "").replace(",", "").replace("_", "")
            amount = float(num_str)
            description = parts[1].strip() if len(parts) > 1 else "без описания"
            add_operation(chat_id, amount, description)
            balance = get_balance(chat_id)
            sign = "➕" if amount > 0 else "➖"
            emoji = "✅" if balance >= 0 else "⚠️"
            await update.message.reply_text(
                f"{sign} `{format_amount(abs(amount))} ₽` — {description}\n"
                f"{emoji} *Касса: {format_amount(balance)} ₽*",
                parse_mode="Markdown"
            )
        except (ValueError, IndexError):
            pass

async def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("касса", kassa_cmd))
    app.add_handler(CommandHandler("kassa", kassa_cmd))
    app.add_handler(CommandHandler("история", history_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("обнулить", reset_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

   
  
