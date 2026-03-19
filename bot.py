import logging
import asyncio
import os
import socket
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ChatJoinRequestHandler, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.request import HTTPXRequest
from telegram.error import RetryAfter, NetworkError, Forbidden

# ================== CONFIG ==================
BOT_TOKEN = "8750408694:AAEP0m8zmfzzpFGWjfXpeabtafNEm69dVyk"
BOT_USERNAME = "Mybtxp_bot"

IMAGES = ["img1.jpg", "img2.jpg", "img3.jpg", "img4.jpg"]
COMPRESSED_FOLDER = "compressed"

# ================== SUBSCRIBER STORAGE ==================
USER_FILE = "subscribers.txt"

def load_users():
    """Load user IDs from file, return as set of ints."""
    if not os.path.exists(USER_FILE):
        return set()
    with open(USER_FILE, "r") as f:
        return {int(line.strip()) for line in f if line.strip()}

def save_users(users):
    """Save user IDs to file."""
    with open(USER_FILE, "w") as f:
        for uid in users:
            f.write(f"{uid}\n")

# Admin IDs – replace with your Telegram user ID(s)
ADMIN_IDS = [8519806292]  # <-- PUT YOUR USER ID HERE

# ================== LOG ==================
logging.basicConfig(level=logging.INFO)

# ================== IMAGE COMPRESS ==================
def compress_image(input_path):
    try:
        if not os.path.exists(COMPRESSED_FOLDER):
            os.makedirs(COMPRESSED_FOLDER)

        output_path = os.path.join(COMPRESSED_FOLDER, os.path.basename(input_path))

        img = Image.open(input_path)
        img.thumbnail((1280, 1280))

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(output_path, "JPEG", quality=80, optimize=True)

        return output_path

    except Exception as e:
        print(f"❌ Compression failed: {input_path} → {e}")
        return input_path

# ================== SAFE SEND ==================
async def safe_send(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)

    except RetryAfter as e:
        await asyncio.sleep(int(e.retry_after))
        return await func(*args, **kwargs)

    except NetworkError:
        await asyncio.sleep(0.5)
        return await func(*args, **kwargs)

    except Exception as e:
        print(f"❌ Send Error: {e}")

# ================== SAFE PHOTO (with keyboard) ==================
async def send_photo_safe(bot, chat_id, img_path, caption, reply_markup=None):
    if not os.path.exists(img_path):
        print(f"⚠️ Image not found: {img_path}, sending only text.")
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", reply_markup=reply_markup)
        return

    try:
        compressed = compress_image(img_path)

        with open(compressed, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"❌ Image Failed → {img_path}: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Store user ID
    users = load_users()
    users.add(user.id)
    save_users(users)
    print(f"✅ New subscriber: {user.id} ({user.full_name})")

    text = (
        f"👑💎 <b>𝙀𝙇𝙄𝙏𝙀 𝙑𝙄𝙋 𝙎𝙔𝙎𝙏𝙀𝙈</b> 💎👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>{user.first_name.upper()}</b>\n"
        f"🔐 <b>ACCESS:</b> Your Bot is running ...\n"
        f"🟢 <b>STATUS:</b> ACTIVE\n\n"
        f"🚀 Premium content Enabled\n"
        f"💎 premium Content uploading soon "
    )

    await update.message.reply_text(text, parse_mode="HTML")

# ================== BROADCAST (admin only) ==================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <your message>")
        return

    text = " ".join(context.args)
    users = load_users()
    if not users:
        await update.message.reply_text("No subscribers yet.")
        return

    await update.message.reply_text(f"Broadcasting to {len(users)} users...")
    success = 0
    failed = 0
    removed = 0

    for uid in list(users):
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Forbidden:
            users.remove(uid)
            removed += 1
            failed += 1
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed += 1

    if removed:
        save_users(users)

    await update.message.reply_text(
        f"✅ Broadcast finished.\n"
        f"📨 Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"🗑️ Removed (blocked): {removed}"
    )

# ================== STORE POSTS (admin only) ==================
async def store_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store any non-command message from admin for later broadcasting."""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return  # ignore non-admin

    # Initialize list in user_data if not present
    if 'pending_posts' not in context.user_data:
        context.user_data['pending_posts'] = []

    message = update.message
    post = {}

    if message.text and not message.text.startswith('/'):  # ignore commands
        post['type'] = 'text'
        post['text'] = message.text
        post['parse_mode'] = 'HTML'  # you can also use message.parse_entities if needed
    elif message.photo:
        # get the largest photo
        photo = message.photo[-1]
        post['type'] = 'photo'
        post['file_id'] = photo.file_id
        post['caption'] = message.caption or ''
        post['parse_mode'] = 'HTML' if message.caption_entities else None
    elif message.video:
        post['type'] = 'video'
        post['file_id'] = message.video.file_id
        post['caption'] = message.caption or ''
        post['parse_mode'] = 'HTML' if message.caption_entities else None
    elif message.document:
        post['type'] = 'document'
        post['file_id'] = message.document.file_id
        post['caption'] = message.caption or ''
        post['parse_mode'] = 'HTML' if message.caption_entities else None
    # You can add audio, animation, etc. similarly
    else:
        # Unsupported type, ignore
        return

    context.user_data['pending_posts'].append(post)
    await update.message.reply_text(f"✅ Post stored. Total pending: {len(context.user_data['pending_posts'])}")

# ================== POST IT (admin only) ==================
async def postit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast all stored posts to subscribers."""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ You are not authorized.")
        return

    if 'pending_posts' not in context.user_data or not context.user_data['pending_posts']:
        await update.message.reply_text("No pending posts to send.")
        return

    posts = context.user_data['pending_posts']
    users = load_users()
    if not users:
        await update.message.reply_text("No subscribers.")
        return

    await update.message.reply_text(f"Sending {len(posts)} posts to {len(users)} subscribers...")

    sent_count = 0
    removed = 0

    for uid in list(users):
        user_sent = 0
        for post in posts:
            try:
                if post['type'] == 'text':
                    await context.bot.send_message(
                        chat_id=uid,
                        text=post['text'],
                        parse_mode=post.get('parse_mode')
                    )
                elif post['type'] == 'photo':
                    await context.bot.send_photo(
                        chat_id=uid,
                        photo=post['file_id'],
                        caption=post['caption'],
                        parse_mode=post.get('parse_mode')
                    )
                elif post['type'] == 'video':
                    await context.bot.send_video(
                        chat_id=uid,
                        video=post['file_id'],
                        caption=post['caption'],
                        parse_mode=post.get('parse_mode')
                    )
                elif post['type'] == 'document':
                    await context.bot.send_document(
                        chat_id=uid,
                        document=post['file_id'],
                        caption=post['caption'],
                        parse_mode=post.get('parse_mode')
                    )
                user_sent += 1
                await asyncio.sleep(0.05)
            except Forbidden:
                users.remove(uid)
                removed += 1
                break  # user blocked, skip remaining posts for this user
            except Exception as e:
                print(f"Failed to send to {uid}: {e}")
                # continue with next post for this user? maybe skip this post only.
        else:
            # If loop completed without break (user not blocked)
            sent_count += 1

    if removed:
        save_users(users)

    await update.message.reply_text(
        f"✅ Broadcasting finished.\n"
        f"📨 Received posts by {sent_count} users\n"
        f"🗑️ Removed (blocked): {removed}"
    )

    # Clear pending posts
    context.user_data['pending_posts'] = []

# ================== CLEAR POSTS (admin only) ==================
async def clear_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    if 'pending_posts' in context.user_data:
        context.user_data['pending_posts'] = []
    await update.message.reply_text("✅ Pending posts cleared.")

# ================== APPROVE ==================
async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user = request.from_user

    try:
        await request.approve()
        name = user.full_name.upper()

        # Store user ID
        users = load_users()
        users.add(user.id)
        save_users(users)
        print(f"✅ New subscriber (via join request): {user.id} ({user.full_name})")

        # ---------- IMAGE 1 ----------
        caption1 = (
            f"💎✨ <b>WELCOME {name}</b> ✨💎\n"
            f"🔥 <b>PREMIUM ACCESS ACTIVATED</b>\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🔹 <b>Main channel</b>\n<b>https://t.me/+eibC-dx2zv44YTQ1</b>\n\n"
            f"🔹 <b>VIP channel</b>\n<b>https://t.me/+Adzj_8V6_6hmOGRl</b>\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Stay connected</b>"
        )
        keyboard1 = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎✦𝗝𝗢𝗜𝗡 𝗔𝗟𝗟✦ ", url="https://t.me/+iKahhNHZgiVjOGQ1")],
            [InlineKeyboardButton("🔥 ✦𝗩𝗜𝗣 𝗖𝗢𝗡𝗧𝗘𝗡𝗧𝗦✦ ", url="https://t.me/+iKahhNHZgiVjOGQ1")]
        ])
        await send_photo_safe(context.bot, user.id, IMAGES[0], caption1, reply_markup=keyboard1)

        # ---------- IMAGE 2 ----------
        caption2 = (
            "━━━━━━━━━━━━━━━━\n"
            "💰 <b>Premium Content</b>\n"
            "🎯 <b>Pro Channels</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔹 <b>Viral Video [1] link</b>\n<b>https://t.me/+44FWzj7TxpNjMGM9</b>\n\n"
            "🔹 <b>Viral Video [2] link</b>\n<b>https://t.me/+MssTCTNtd1xjNjNl</b>\n\n"
            "━━━━━━━━━━━━━━━━"
        )
        keyboard2 = InlineKeyboardMarkup([
            [InlineKeyboardButton(" ★𝗧𝗿𝗲𝗻𝗱𝗶𝗻𝗴 𝗥𝗲𝗲𝗹𝘀★ ", url="https://t.me/+ttO0UPPxodk4OTBl")],
            [InlineKeyboardButton(" ★𝗙𝘂𝗹𝗹 𝗩𝗶𝗱𝗲𝗼𝘀 ★", url="https://t.me/+ttO0UPPxodk4OTBl")]
        ])
        await send_photo_safe(context.bot, user.id, IMAGES[1], caption2, reply_markup=keyboard2)

        # ---------- IMAGE 3 ----------
        caption3 = (
            " <b>For Instagram:</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "1️⃣ <b>Trending Videos</b>\n<b>https://t.me/+i2aAcDajdpc1MmE1</b>\n\n"
            "2️⃣ <b>All reels full videos</b>\n<b>https://t.me/+5fXdVA8Uc780YTJl</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            " <b>Fallow steps = Premium access</b>"
        )
        keyboard3 = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ✰𝗖𝗵𝗮𝗻𝗻𝗲𝗹 [𝗛𝗗]✰  ", url="https://t.me/+iKahhNHZgiVjOGQ1")],
            [InlineKeyboardButton("💎 ✰𝗙𝗿𝗲𝗲(100%) ✰  ", url="https://t.me/+iKahhNHZgiVjOGQ1")]
        ])
        await send_photo_safe(context.bot, user.id, IMAGES[2], caption3, reply_markup=keyboard3)

        # ---------- IMAGE 4 ----------
        caption4 = (
            "🎁 <b>Click below to claim bonus</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔹 <b>Trending channel</b>\n<b>https://t.me/+uX6WL950EaBkYjJl</b>\n\n"
            f"🔹 <b>click Here for More </b>\n<b>https://t.me/{BOT_USERNAME}?start=vip</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🚀💎 <b>FINAL STEP</b>\n\n"
            "👇 <b>START BOT NOW For Videos</b> 👇"
        )
        keyboard4 = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 𝐒𝐓𝐀𝐑𝐓 𝐁𝐎𝐓 🔥", url=f"https://t.me/{BOT_USERNAME}?start=vip")]
        ])
        await send_photo_safe(context.bot, user.id, IMAGES[3], caption4, reply_markup=keyboard4)

    except Exception as e:
        print(f"❌ Error approving request: {e}")

# ================== SCHEDULED POST ==================
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

async def scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    """Example scheduled post – runs daily at 10:00 AM."""
    users = load_users()
    if not users:
        return
    text = (
        "🔥 <b>Daily Update</b>\n\n"
        "New premium content is waiting for you!\n"
        "👉 Check it out now!"
    )
    success = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Forbidden:
            users.remove(uid)
        except Exception as e:
            print(f"Scheduled post failed for {uid}: {e}")
    save_users(users)
    print(f"Scheduled post sent to {success} users.")

# ================== POST INIT ==================
async def post_init(application: Application) -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_post,
        CronTrigger(hour=10, minute=0),   # change as needed
        args=[application.bot]
    )
    scheduler.start()
    print("⏰ Scheduler started (daily at 10:00).")

# ================== MAIN ==================
def main():
    def can_connect_to_telegram():
        try:
            socket.create_connection(("api.telegram.org", 443), timeout=5)
            return True
        except OSError:
            return False

    if not can_connect_to_telegram():
        print("\n❌ No internet connection or cannot reach api.telegram.org")
        print("👉 Please check:")
        print("   - Your internet connection")
        print("   - Firewall/antivirus (allow Python)")
        print("   - DNS settings (try 8.8.8.8)")
        print("   - If behind a proxy, configure it in the code\n")
        return

    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("postit", postit))
    app.add_handler(CommandHandler("clear_posts", clear_posts))
    app.add_handler(ChatJoinRequestHandler(approve_request))

    # Message handler to store posts from admin (non-command messages)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, store_post))

    print("💎 PREMIUM BOT STARTING... 🚀")
    try:
        app.run_polling(bootstrap_retries=3)
    except Exception as e:
        print(f"\n❌ Bot crashed: {e}")
        print("👉 Still having issues? Try running with a VPN or check your network.")

if __name__ == "__main__":
    main()