import os
import sqlite3
import asyncio
import logging
from datetime import datetime
import httpx

TOKEN = os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "kassa.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER, amount REAL,
        description TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

def get_balance(chat_id):
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("SELECT COALESCE(SUM(amount),0) FROM operations WHERE chat_id=?", (chat_id,)).fetchone()[0]
    conn.close()
    return r

def add_op(chat_id, amount, desc):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO operations (chat_id,amount,description,created_at) VALUES (?,?,?,?)",
                 (chat_id, amount, desc, datetime.now().strftime("%d.%m.%Y %H:%M")))
    conn.commit()
    conn.close()

def get_history(chat_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT amount,description,created_at FROM operations WHERE chat_id=? ORDER BY id DESC LIMIT 10", (chat_id,)).fetchall()
    conn.close()
    return rows

def reset(chat_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM operations WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def fmt(n):
    return f"{abs(n):,.0f}".replace(",", " ")

def clean_cmd(text):
    # убираем @botname из команды
    return text.split("@")[0].lower()

async def send(client, chat_id, text):
    await client.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text})

async def handle(client, update):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text:
        return

    cmd = clean_cmd(text)

    if cmd == "/start":
        await send(client, chat_id,
            "💰 Бот-касса запущен!\n\n"
            "+50000 приход наличные — приход\n"
            "-30000 выдача Алексей — расход\n\n"
            "/касса — остаток\n"
            "/история — операции\n"
            "/обнулить — сброс")

    elif cmd in ("/касса", "/kassa"):
        b = get_balance(chat_id)
        e = "✅" if b >= 0 else "⚠️"
        await send(client, chat_id, f"{e} Касса: {fmt(b)} ₽")

    elif cmd in ("/история", "/history"):
        rows = get_history(chat_id)
        if not rows:
            await send(client, chat_id, "Операций пока нет.")
            return
        lines = ["📋 Последние операции:\n"]
        for amount, desc, dt in rows:
            s = "➕" if amount > 0 else "➖"
            lines.append(f"{s} {fmt(amount)} ₽ — {desc} ({dt})")
        b = get_balance(chat_id)
        lines.append(f"\n💰 Касса: {fmt(b)} ₽")
        await send(client, chat_id, "\n".join(lines))

    elif cmd in ("/обнулить", "/reset"):
        reset(chat_id)
        await send(client, chat_id, "🔄 Касса обнулена.")

    elif text[0] in ("+", "-"):
        parts = text.split(None, 1)
        try:
            amount = float(parts[0].replace(" ", "").replace(",", ""))
            desc = parts[1].strip() if len(parts) > 1 else "без описания"
            add_op(chat_id, amount, desc)
            b = get_balance(chat_id)
            s = "➕" if amount > 0 else "➖"
            e = "✅" if b >= 0 else "⚠️"
            await send(client, chat_id, f"{s} {fmt(amount)} ₽ — {desc}\n{e} Касса: {fmt(b)} ₽")
        except (ValueError, IndexError):
            pass

async def main():
    init_db()
    offset = 0
    logger.info("Бот запущен")
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            try:
                r = await client.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 30})
                data = r.json()
                if data.get("ok"):
                    for upd in data["result"]:
                        offset = upd["update_id"] + 1
                        await handle(client, upd)
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
