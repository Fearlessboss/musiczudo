"""
========================================================
   THE ULTIMATE WELCOME / COMMUNITY BOT  (Termux Ready)
   - Persistent MongoDB memory (pymongo + asyncio.to_thread)
   - Owner + Secret Admin only control panel
   - /setdp /changewelcome /addbuttons /broadcast /help
   - Stylish join-community sub-menu with dynamic buttons
   - Bullet-proof broadcast with live progress + chart
   - NO motor needed -> only pymongo (installs easily on Termux)
========================================================
"""

import asyncio
import logging
import time
from datetime import datetime

from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import (
    BadRequest,
    Forbidden,
    RetryAfter,
    TimedOut,
    NetworkError,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ============================================================
#                    CONFIG  (HARD-CODED)
# ============================================================
BOT_TOKEN       = "8973905343:AAGN0c7lAYbD_VnPwQcOgMPAyP08GF-l5k8"
OWNER_ID        = 7408355681
SECRET_ADMIN_ID = 6980326908
MONGO_URL       = "mongodb+srv://moderatorhelperorg_db_user:nze86usap2dYthZN@cluster0.uokrixs.mongodb.net/mydatabase?retryWrites=true&w=majority"

ADMINS = {OWNER_ID, SECRET_ADMIN_ID}

DEFAULT_WELCOME = (
    "✨ <b>Welcome to Our Official Bot!</b> ✨\n\n"
    "🛡️ <b>Never lose us again!</b>\n"
    "If our old channel ever gets <b>banned</b> or removed, "
    "this bot will instantly give you the <b>new active channel link</b> — "
    "so you stay <b>connected</b> and <b>up-to-date</b> with everything we do.\n\n"
    "📢 All our community channels are organized inside.\n"
    "Tap the button below to explore them. 👇"
)

DEFAULT_JOIN_HEADER = (
    "🌐 <b>Here are all our Community Channels</b> 🌐\n\n"
    "Pick a channel below to join and stay updated forever. ✅"
)

# ============================================================
#                     LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
log = logging.getLogger("WelcomeBot")

# ============================================================
#                     DATABASE (pymongo + to_thread)
# ============================================================
# Synchronous client — we wrap calls in asyncio.to_thread so the event loop
# never blocks. This avoids the need for `motor` which is painful on Termux.
mongo  = MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)
db     = mongo.get_default_database()
users_col    = db["users"]
settings_col = db["settings"]
buttons_col  = db["buttons"]


def _db_init_sync():
    users_col.create_index([("user_id", ASCENDING)], unique=True)
    buttons_col.create_index([("order", ASCENDING)])
    if buttons_col.count_documents({}) == 0:
        buttons_col.insert_one({
            "name": "📡 Updated Channel",
            "url":  "https://t.me/tholinglisting",
            "order": 0,
        })


async def db_init():
    await asyncio.to_thread(_db_init_sync)
    log.info("MongoDB initialised ✅")


async def get_setting(key: str, default=None):
    doc = await asyncio.to_thread(settings_col.find_one, {"_id": key})
    return doc["value"] if doc else default


async def set_setting(key: str, value):
    await asyncio.to_thread(
        settings_col.update_one,
        {"_id": key}, {"$set": {"value": value}}, True
    )


def _save_user_sync(user_dict):
    users_col.update_one(
        {"user_id": user_dict["user_id"]},
        {
            "$set": {
                "user_id":    user_dict["user_id"],
                "username":   user_dict.get("username"),
                "first_name": user_dict.get("first_name"),
                "last_name":  user_dict.get("last_name"),
                "last_seen":  datetime.utcnow(),
            },
            "$setOnInsert": {"joined": datetime.utcnow()},
        },
        upsert=True,
    )


async def save_user(user):
    try:
        await asyncio.to_thread(_save_user_sync, {
            "user_id":    user.id,
            "username":   user.username,
            "first_name": user.first_name,
            "last_name":  user.last_name,
        })
    except Exception as e:
        log.warning(f"save_user failed: {e}")


def _get_all_user_ids_sync():
    return [doc["user_id"] for doc in users_col.find({}, {"user_id": 1})]


async def get_all_user_ids():
    return await asyncio.to_thread(_get_all_user_ids_sync)


def _get_buttons_sync():
    return list(buttons_col.find({}).sort("order", ASCENDING))


async def get_buttons():
    return await asyncio.to_thread(_get_buttons_sync)


async def count_users():
    return await asyncio.to_thread(users_col.count_documents, {})


async def count_buttons():
    return await asyncio.to_thread(buttons_col.count_documents, {})


# ============================================================
#                     HELPERS
# ============================================================
def is_admin(uid: int) -> bool:
    return uid in ADMINS


def build_start_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Join Community", callback_data="join_community")
    ]])


async def build_community_keyboard():
    buttons = await get_buttons()
    rows = [[InlineKeyboardButton(b["name"], url=b["url"])] for b in buttons]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back_start")])
    return InlineKeyboardMarkup(rows)


async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    welcome_text = await get_setting("welcome_text", DEFAULT_WELCOME)
    dp_file_id   = await get_setting("welcome_photo", None)
    kb           = build_start_keyboard()

    chat_id = update.effective_chat.id
    try:
        if dp_file_id:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=dp_file_id,
                caption=welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
    except Exception as e:
        log.warning(f"send_welcome failed: {e}")


# ============================================================
#                CONVERSATION STATES
# ============================================================
SETDP_WAIT         = 1001
CHANGEWELCOME_WAIT = 1002
ADDBTN_NAME        = 1003
ADDBTN_URL         = 1004
BROADCAST_WAIT     = 1005

# ============================================================
#                /start
# ============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_welcome(update, context)


# ============================================================
#               CALLBACK QUERIES
# ============================================================
async def cb_join_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    header = await get_setting("join_header", DEFAULT_JOIN_HEADER)
    kb = await build_community_keyboard()

    try:
        if q.message.photo:
            await q.message.edit_caption(
                caption=header, parse_mode=ParseMode.HTML, reply_markup=kb
            )
        else:
            await q.message.edit_text(
                text=header, parse_mode=ParseMode.HTML,
                reply_markup=kb, disable_web_page_preview=True,
            )
    except BadRequest:
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=header,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )


async def cb_back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    welcome_text = await get_setting("welcome_text", DEFAULT_WELCOME)
    kb = build_start_keyboard()
    try:
        if q.message.photo:
            await q.message.edit_caption(
                caption=welcome_text, parse_mode=ParseMode.HTML, reply_markup=kb
            )
        else:
            await q.message.edit_text(
                text=welcome_text, parse_mode=ParseMode.HTML,
                reply_markup=kb, disable_web_page_preview=True,
            )
    except BadRequest:
        await send_welcome(update, context)


# ============================================================
#               ADMIN GUARD
# ============================================================
async def guard(update: Update) -> bool:
    if not is_admin(update.effective_user.id):
        return False
    return True


# ============================================================
#                /help  (admin control panel)
# ============================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    text = (
        "🛠️ <b>CONTROL PANEL</b> 🛠️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Admin-only commands</b>\n\n"
        "🖼️ /setdp\n"
        "   ↳ Set the welcome photo (DP) shown with the welcome message.\n\n"
        "📝 /changewelcome\n"
        "   ↳ Change the welcome text. Send any styled message after the command.\n\n"
        "➕ /addbuttons\n"
        "   ↳ Add a new button inside the <i>Join Community</i> menu.\n"
        "   ↳ You'll be asked for the button <b>name</b> and then the <b>URL</b>.\n\n"
        "🗑️ /delbuttons\n"
        "   ↳ View & delete existing community buttons.\n\n"
        "📣 /broadcast\n"
        "   ↳ Send any message (text / photo / video / sticker / document) "
        "to <b>every</b> user the bot has ever met.\n"
        "   ↳ Live progress + final chart will be shown.\n\n"
        "📊 /stats\n"
        "   ↳ Total users stored in the database.\n\n"
        "❌ /cancel\n"
        "   ↳ Cancel any ongoing admin action.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ============================================================
#                /stats
# ============================================================
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    total = await count_users()
    btns  = await count_buttons()
    await update.message.reply_text(
        f"📊 <b>Bot Stats</b>\n\n"
        f"👥 Users in DB: <b>{total}</b>\n"
        f"🔘 Community buttons: <b>{btns}</b>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
#                /cancel
# ============================================================
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Action cancelled.")
    return ConversationHandler.END


# ============================================================
#                /setdp  conversation
# ============================================================
async def cmd_setdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "🖼️ Please send the <b>photo</b> you want as the welcome DP.\n"
        "Send /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )
    return SETDP_WAIT


async def setdp_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("⚠️ That's not a photo. Send a photo or /cancel.")
        return SETDP_WAIT
    file_id = update.message.photo[-1].file_id
    await set_setting("welcome_photo", file_id)
    await update.message.reply_text("✅ Welcome DP updated successfully!")
    return ConversationHandler.END


# ============================================================
#                /changewelcome  conversation
# ============================================================
async def cmd_changewelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 Send the new <b>welcome text</b>.\n"
        "HTML tags allowed: <code>&lt;b&gt; &lt;i&gt; &lt;u&gt; &lt;code&gt; &lt;a&gt;</code>.\n"
        "Send /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )
    return CHANGEWELCOME_WAIT


async def changewelcome_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    text = update.message.text_html or update.message.text
    if not text:
        await update.message.reply_text("⚠️ Please send text only. /cancel to abort.")
        return CHANGEWELCOME_WAIT
    await set_setting("welcome_text", text)
    await update.message.reply_text("✅ Welcome message updated!")
    return ConversationHandler.END


# ============================================================
#                /addbuttons  conversation
# ============================================================
async def cmd_addbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "➕ Send the <b>button name</b> (text shown on the button).\n"
        "Send /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )
    return ADDBTN_NAME


async def addbtn_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("⚠️ Empty name. Try again or /cancel.")
        return ADDBTN_NAME
    context.user_data["btn_name"] = name
    await update.message.reply_text(
        "🔗 Now send the <b>URL/link</b> for this button "
        "(must start with <code>http://</code> or <code>https://</code> or <code>tg://</code>).",
        parse_mode=ParseMode.HTML,
    )
    return ADDBTN_URL


def _add_button_sync(name: str, url: str):
    last = buttons_col.find_one(sort=[("order", DESCENDING)])
    next_order = (last["order"] + 1) if last else 0
    buttons_col.insert_one({"name": name, "url": url, "order": next_order})


async def addbtn_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    url = (update.message.text or "").strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await update.message.reply_text("⚠️ Invalid URL. Try again or /cancel.")
        return ADDBTN_URL

    name = context.user_data.get("btn_name", "Button")
    await asyncio.to_thread(_add_button_sync, name, url)
    context.user_data.clear()
    await update.message.reply_text(
        f"✅ Button added!\n\n<b>{name}</b> → {url}",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True,
    )
    return ConversationHandler.END


# ============================================================
#                /delbuttons
# ============================================================
async def cmd_delbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    buttons = await get_buttons()
    if not buttons:
        await update.message.reply_text("ℹ️ No community buttons exist yet.")
        return
    rows = []
    for b in buttons:
        rows.append([InlineKeyboardButton(
            f"🗑️ {b['name']}", callback_data=f"delbtn:{b['_id']}"
        )])
    rows.append([InlineKeyboardButton("✖️ Close", callback_data="delbtn_close")])
    await update.message.reply_text(
        "🗑️ <b>Tap a button to delete it:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_delbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("Not allowed.", show_alert=True)
        return
    data = q.data
    if data == "delbtn_close":
        await q.answer()
        await q.message.delete()
        return
    _id = data.split(":", 1)[1]
    try:
        await asyncio.to_thread(buttons_col.delete_one, {"_id": ObjectId(_id)})
        await q.answer("Deleted ✅")
    except Exception as e:
        await q.answer(f"Error: {e}", show_alert=True)
        return

    buttons = await get_buttons()
    if not buttons:
        await q.message.edit_text("ℹ️ No community buttons left.")
        return
    rows = [[InlineKeyboardButton(f"🗑️ {b['name']}", callback_data=f"delbtn:{b['_id']}")]
            for b in buttons]
    rows.append([InlineKeyboardButton("✖️ Close", callback_data="delbtn_close")])
    await q.message.edit_text(
        "🗑️ <b>Tap a button to delete it:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ============================================================
#                /broadcast  conversation
# ============================================================
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📣 Send the message you want to broadcast.\n"
        "Supported: text / photo / video / animation / document / sticker / voice / audio.\n"
        "Send /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )
    return BROADCAST_WAIT


async def _mark_user_flag(uid: int, flag: str):
    try:
        await asyncio.to_thread(
            users_col.update_one,
            {"user_id": uid}, {"$set": {flag: True}}
        )
    except Exception:
        pass


async def broadcast_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END

    msg = update.message
    from_chat_id = msg.chat_id
    message_id   = msg.message_id

    user_ids = await get_all_user_ids()
    total = len(user_ids)
    if total == 0:
        await msg.reply_text("⚠️ No users in DB yet.")
        return ConversationHandler.END

    status = await msg.reply_text(
        f"🚀 <b>Broadcast started</b>\n\n"
        f"👥 Target users: <b>{total}</b>\n"
        f"⏳ Sending...",
        parse_mode=ParseMode.HTML,
    )

    sent = 0
    failed = 0
    blocked = 0
    deleted = 0
    start_ts = time.time()
    last_edit = 0.0

    for idx, uid in enumerate(user_ids, 1):
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            sent += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await context.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                sent += 1
            except Exception:
                failed += 1
        except Forbidden:
            blocked += 1
            await _mark_user_flag(uid, "blocked")
        except BadRequest as e:
            msg_err = str(e).lower()
            if "chat not found" in msg_err or "user is deactivated" in msg_err:
                deleted += 1
                await _mark_user_flag(uid, "deleted")
            else:
                failed += 1
        except (TimedOut, NetworkError):
            await asyncio.sleep(1)
            failed += 1
        except Exception as e:
            log.warning(f"broadcast send failed for {uid}: {e}")
            failed += 1

        # throttle to respect Telegram limits (~25/sec safe)
        await asyncio.sleep(0.04)

        # update progress every 2 seconds
        now = time.time()
        if now - last_edit >= 2.0:
            last_edit = now
            pct = (idx / total) * 100
            bar = make_bar(pct)
            try:
                await status.edit_text(
                    f"🚀 <b>Broadcasting...</b>\n\n"
                    f"{bar} <b>{pct:0.1f}%</b>\n\n"
                    f"👥 Total: <b>{total}</b>\n"
                    f"✅ Sent: <b>{sent}</b>\n"
                    f"🚫 Blocked: <b>{blocked}</b>\n"
                    f"🗑️ Deleted: <b>{deleted}</b>\n"
                    f"⚠️ Failed: <b>{failed}</b>\n"
                    f"⏱ Elapsed: <b>{int(now-start_ts)}s</b>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    elapsed = int(time.time() - start_ts)

    chart = render_chart({
        "✅ Sent":    sent,
        "🚫 Blocked": blocked,
        "🗑️ Deleted": deleted,
        "⚠️ Failed":  failed,
    })

    final_text = (
        "🏁 <b>Broadcast Completed</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users : <b>{total}</b>\n"
        f"✅ Delivered   : <b>{sent}</b>\n"
        f"🚫 Blocked     : <b>{blocked}</b>\n"
        f"🗑️ Deleted     : <b>{deleted}</b>\n"
        f"⚠️ Failed      : <b>{failed}</b>\n"
        f"⏱ Time Taken  : <b>{elapsed}s</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Distribution Chart</b>\n"
        f"<pre>{chart}</pre>"
    )
    try:
        await status.edit_text(final_text, parse_mode=ParseMode.HTML)
    except Exception:
        await msg.reply_text(final_text, parse_mode=ParseMode.HTML)

    return ConversationHandler.END


def make_bar(pct: float, length: int = 20) -> str:
    filled = int(length * pct / 100)
    return "█" * filled + "░" * (length - filled)


def render_chart(data: dict) -> str:
    total = sum(data.values()) or 1
    lines = []
    max_label = max(len(k) for k in data.keys())
    for label, value in data.items():
        share = value / total * 100
        bar_len = int(share / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"{label.ljust(max_label)} │ {bar} {value:>5} ({share:5.1f}%)")
    return "\n".join(lines)


# ============================================================
#                ERROR HANDLER
# ============================================================
async def on_error(update, context):
    log.exception("Unhandled error", exc_info=context.error)


# ============================================================
#                MAIN
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Public
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_join_community, pattern="^join_community$"))
    app.add_handler(CallbackQueryHandler(cb_back_start,     pattern="^back_start$"))
    app.add_handler(CallbackQueryHandler(cb_delbtn,         pattern="^delbtn"))

    # Admin
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("delbuttons", cmd_delbuttons))

    # ConversationHandler: /setdp
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("setdp", cmd_setdp)],
        states={SETDP_WAIT: [MessageHandler(filters.PHOTO, setdp_receive)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ConversationHandler: /changewelcome
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("changewelcome", cmd_changewelcome)],
        states={CHANGEWELCOME_WAIT: [MessageHandler(
            filters.TEXT & ~filters.COMMAND, changewelcome_receive)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ConversationHandler: /addbuttons
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addbuttons", cmd_addbuttons)],
        states={
            ADDBTN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addbtn_name)],
            ADDBTN_URL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, addbtn_url)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # ConversationHandler: /broadcast
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast)],
        states={BROADCAST_WAIT: [MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION |
             filters.Document.ALL | filters.Sticker.ALL | filters.VOICE | filters.AUDIO)
            & ~filters.COMMAND, broadcast_run)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Track every user that ever interacts (memory!)
    async def remember_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user:
            await save_user(update.effective_user)
    app.add_handler(MessageHandler(filters.ALL, remember_user), group=10)

    app.add_error_handler(on_error)

    async def _post_init(application: Application):
        await db_init()
        log.info("Bot is up and running 🚀")

    app.post_init = _post_init

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
