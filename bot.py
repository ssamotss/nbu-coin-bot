import sqlite3
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# =====================
# CONFIG
# =====================
TOKEN = "Y8723483788:AAFO2gHmrPfUNL2sdKVm1uCBI-SQtuSqCdA"
CATALOG_URL = "https://coins.bank.gov.ua/catalog.html"
BASE_URL = "https://coins.bank.gov.ua"
USER_ID = 656586028  # твій ID

# =====================
# DB
# =====================
conn = sqlite3.connect("data.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS coins (
    url TEXT PRIMARY KEY,
    name TEXT,
    stock INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tracked_coins (
    url TEXT PRIMARY KEY
)
""")
conn.commit()

# =====================
# MENU
# =====================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪙 Каталог", callback_data="catalog|0")],
        [InlineKeyboardButton("⭐ Мої монети", callback_data="my")],
        [InlineKeyboardButton("🔄 Оновити", callback_data="refresh")]
    ])

back_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
])

# =====================
# FETCH CATALOG
# =====================
def fetch_catalog():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(CATALOG_URL, headers=headers, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    coins = []
    for a in soup.select("a[href*='/p-']"):
        name = a.get_text(strip=True)
        href = a.get("href")
        if not name or not href:
            continue
        coins.append({"url": BASE_URL + href, "name": name})
    return coins

# =====================
# STOCK
# =====================
def get_stock(url):
    try:
        r = requests.get(url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        el = soup.find("span", class_="pd_qty")
        return int(el.text.strip()) if el else 0
    except Exception:
        return 0

# =====================
# START
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню:", reply_markup=menu())

# =====================
# CALLBACK
# =====================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "menu":
        await q.edit_message_text("Меню:", reply_markup=menu())

    elif data == "refresh":
        coins = fetch_catalog()
        for c in coins:
            cur.execute("""
                INSERT OR REPLACE INTO coins (url, name, stock)
                VALUES (?, ?, COALESCE((SELECT stock FROM coins WHERE url=?), 0))
            """, (c["url"], c["name"], c["url"]))
        conn.commit()
        await q.edit_message_text(f"🔄 Оновлено: {len(coins)} монет", reply_markup=back_menu)

    elif data.startswith("catalog|"):
        page = int(data.split("|")[1])
        cur.execute("SELECT url, name FROM coins LIMIT 30 OFFSET ?", (page * 30,))
        rows = cur.fetchall()
        if not rows:
            await q.edit_message_text("Каталог пустий", reply_markup=back_menu)
            return
        keyboard = [[InlineKeyboardButton(name[:50], callback_data=f"view|{url}")] for url, name in rows]
        if page > 0:
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"catalog|{page-1}")])
        keyboard.append([InlineKeyboardButton("➡️ Далі", callback_data=f"catalog|{page+1}")])
        keyboard.append([InlineKeyboardButton("⬅️ Меню", callback_data="menu")])
        await q.edit_message_text("🪙 Каталог:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("view|"):
        url = data.split("|")[1]
        cur.execute("SELECT name FROM coins WHERE url=?", (url,))
        row = cur.fetchone()
        if not row:
            await q.edit_message_text("Не знайдено", reply_markup=back_menu)
            return
        keyboard = [
            [InlineKeyboardButton("🔔 Відстежувати", callback_data=f"track|{url}")],
            [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
        ]
        await q.edit_message_text(f"🪙 {row[0]}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("track|"):
        url = data.split("|")[1]
        cur.execute("INSERT OR REPLACE INTO tracked_coins (url) VALUES (?)", (url,))
        conn.commit()
        cur.execute("SELECT name FROM coins WHERE url=?", (url,))
        row = cur.fetchone()
        await q.edit_message_text(f"✅ Тепер відстежується:\n{row[0]}", reply_markup=back_menu)

    elif data == "my":
        cur.execute("SELECT c.name, c.stock FROM coins c JOIN tracked_coins t ON c.url=t.url")
        rows = cur.fetchall()
        if not rows:
            await q.edit_message_text("Порожньо", reply_markup=back_menu)
            return
        text = "⭐ Монети:\n\n" + "\n".join([f"{name}\n{stock} шт\n" for name, stock in rows])
        await q.edit_message_text(text, reply_markup=back_menu)

# =====================
# MONITOR
# =====================
async def check_stock(context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    cur.execute("SELECT url, name, stock FROM coins")
    rows = cur.fetchall()
    for url, name, old_stock in rows:
        stock = get_stock(url)
        if old_stock == 0 and stock > 0:
            cur.execute("SELECT 1 FROM tracked_coins WHERE url=?", (url,))
            if cur.fetchone():
                await app.bot.send_message(chat_id=USER_ID, text=f"🔔 Є в наявності!\n\n{name}\n{stock} шт\n{url}")
        cur.execute("UPDATE coins SET stock=? WHERE url=?", (stock, url))
    conn.commit()

# =====================
# MAIN
# =====================
def main():
    print("BOT STARTED")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.job_queue.run_repeating(check_stock, interval=300, first=10)
    app.run_polling()

if __name__ == "__main__":
    main()
