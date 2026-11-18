import os
import sqlite3
from datetime import datetime, date

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6113004477

CHANNELS = [
    "@target_freeroot",
    "@scanner33335",
    "@allofficialloot"
]

DB = "primecash.db"

conn = sqlite3.connect(DB)
conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    referred_by INTEGER,
    joined_reward INTEGER DEFAULT 0,
    referral_paid INTEGER DEFAULT 0
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    upi TEXT,
    status TEXT,
    created TEXT
)
""")
conn.commit()


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 My Balance", callback_data="balance"),
         InlineKeyboardButton("🔗 My Referral Link", callback_data="ref")],
        [InlineKeyboardButton("📢 Join 3 Channels", callback_data="join"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("📜 Payment History", callback_data="history")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    referrer = None
    if context.args:
        try:
            referrer = int(context.args[0])
        except ValueError:
            pass

    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id=?", (uid,))
    exists = cur.fetchone()

    if not exists:
        if referrer and referrer != uid:
            cur.execute(
                "INSERT INTO users(id, referred_by) VALUES(?,?)",
                (uid, referrer)
            )
        else:
            cur.execute("INSERT INTO users(id) VALUES(?)", (uid,))
        conn.commit()

    await update.message.reply_text(
        "🎉 Welcome to Prime Cash Earning Bot!\n\n"
        "💰 Join 3 Channels = ₹5\n"
        "👥 Per Referral = ₹4\n"
        "💸 Minimum Withdrawal = ₹10\n\n"
        "Choose an option below:",
        reply_markup=menu()
    )


async def check_join(uid):
    for channel in CHANNELS:
        try:
            member = await app.bot.get_chat_member(channel, uid)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data
    cur = conn.cursor()

    if data == "join":
        links = "\n".join(
            [f"👉 https://t.me/{c[1:]}" for c in CHANNELS]
        )

        await query.message.reply_text(
            "📢 Join all 3 channels:\n\n" + links +
            "\n\nAfter joining, click Verify.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Joining", callback_data="verify")]
            ])
        )

    elif data == "verify":
        if await check_join(uid):
            cur.execute(
                "SELECT joined_reward, referred_by FROM users WHERE id=?",
                (uid,)
            )
            row = cur.fetchone()

            if row and row[0] == 0:
                cur.execute(
                    "UPDATE users SET balance=balance+5, joined_reward=1 WHERE id=?",
                    (uid,)
                )

                referrer = row[1]

                if referrer:
                    cur.execute(
                        "SELECT id FROM users WHERE id=?", (referrer,)
                    )
                    if cur.fetchone():
                        cur.execute(
                            "UPDATE users SET balance=balance+4 WHERE id=?",
                            (referrer,)
                        )
                        cur.execute(
                            "UPDATE users SET referral_paid=1 WHERE id=?",
                            (uid,)
                        )

                conn.commit()

                await query.message.reply_text(
                    "🎉 Verification successful!\n₹5 added to your balance."
                )
            else:
                await query.message.reply_text(
                    "✅ You have already received your joining reward."
                )
        else:
            await query.message.reply_text(
                "❌ Please join all 3 channels first."
            )

    elif data == "balance":
        cur.execute("SELECT balance FROM users WHERE id=?", (uid,))
        row = cur.fetchone()
        balance = row[0] if row else 0

        await query.message.reply_text(
            f"💰 Your Balance: ₹{balance:.2f}"
        )

    elif data == "ref":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={uid}"

        await query.message.reply_text(
            f"🔗 Your Referral Link:\n\n{link}\n\n"
            "👥 Each verified referral earns ₹4."
        )

    elif data == "withdraw":
        context.user_data["state"] = "amount"

        await query.message.reply_text(
            "💸 Enter withdrawal amount.\n"
            "Minimum withdrawal: ₹10"
        )

    elif data == "history":
        cur.execute(
            "SELECT amount, upi, status, created FROM withdrawals "
            "WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (uid,)
        )
        rows = cur.fetchall()

        if not rows:
            await query.message.reply_text("No payment history found.")
        else:
            msg = "📜 Payment History:\n\n"
            for amount, upi, status, created in rows:
                msg += (
                    f"Amount: ₹{amount}\n"
                    f"UPI: {upi}\n"
                    f"Status: {status}\n"
                    f"Date: {created}\n\n"
                )

            await query.message.reply_text(msg)

    elif data.startswith("wd:"):
        if uid != ADMIN_ID:
            return

        action, wid = data.split(":")[1:]
        cur.execute(
            "SELECT user_id, amount, status FROM withdrawals WHERE id=?",
            (int(wid),)
        )
        row = cur.fetchone()

        if not row or row[2] != "Pending":
            await query.message.reply_text("Request already processed.")
            return

        user_id, amount, status = row

        if action == "approve":
            cur.execute(
                "UPDATE withdrawals SET status='Approved' WHERE id=?",
                (int(wid),)
            )
            message = "✅ Your withdrawal has been approved. Admin must send payment separately."

        else:
            cur.execute(
                "UPDATE withdrawals SET status='Rejected' WHERE id=?",
                (int(wid),)
            )
            cur.execute(
                "UPDATE users SET balance=balance+? WHERE id=?",
                (amount, user_id)
            )
            message = "❌ Your withdrawal was rejected. Amount refunded."

        conn.commit()

        try:
            await context.bot.send_message(user_id, message)
        except Exception:
            pass

        await query.message.reply_text("Request processed successfully.")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    cur = conn.cursor()

    if state == "amount":
        try:
            amount = float(update.message.text)
        except ValueError:
            await update.message.reply_text("Enter a valid amount.")
            return

        if amount < 10:
            await update.message.reply_text("Minimum withdrawal is ₹10.")
            return

        cur.execute("SELECT balance FROM users WHERE id=?", (uid,))
        row = cur.fetchone()

        if not row or row[0] < amount:
            await update.message.reply_text("❌ Insufficient balance.")
            return

        context.user_data["amount"] = amount
        context.user_data["state"] = "upi"

        await update.message.reply_text("Enter your UPI ID:")
        return

    if state == "upi":
        upi = update.message.text.strip()

        if len(upi) > 100 or " " in upi or "@" not in upi:
            await update.message.reply_text("Enter a valid UPI ID.")
            return

        amount = context.user_data["amount"]

        today = date.today().isoformat()

        cur.execute(
            "SELECT id FROM withdrawals WHERE user_id=? AND substr(created,1,10)=?",
            (uid, today)
        )

        if cur.fetchone():
            await update.message.reply_text(
                "❌ You can withdraw only once per day."
            )
            context.user_data.clear()
            return

        cur.execute(
            "UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
            (amount, uid, amount)
        )

        if cur.rowcount == 0:
            conn.rollback()
            await update.message.reply_text("Insufficient balance.")
            context.user_data.clear()
            return

        cur.execute(
            "INSERT INTO withdrawals(user_id,amount,upi,status,created) "
            "VALUES(?,?,?,'Pending',?)",
            (uid, amount, upi, datetime.now().isoformat())
        )

        wid = cur.lastrowid
        conn.commit()
        context.user_data.clear()

        await update.message.reply_text(
            "✅ Withdrawal request submitted!\n"
            f"Amount: ₹{amount}\nUPI: {upi}\nStatus: Pending"
        )

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 New Withdrawal Request\n\n"
            f"User: {uid}\nAmount: ₹{amount}\nUPI: {upi}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve", callback_data=f"wd:approve:{wid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject", callback_data=f"wd:reject:{wid}"
                    )
                ]
            ])
        )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT SUM(balance) FROM users")
    balance = cur.fetchone()[0] or 0

    await update.message.reply_text(
        f"👑 PRIME CASH ADMIN PANEL\n\n"
        f"Total Users: {users}\n"
        f"Total User Balance: ₹{balance:.2f}"
    )


if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing!")

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Prime Cash Bot Started!")
app.run_polling()
