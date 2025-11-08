import asyncio
import logging
import re
from datetime import datetime
from aiohttp import web
import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.error import TelegramError

from database import Database
from config import BOT_TOKEN, ADMIN_ID, PORT, SELF_URL, KEEP_ALIVE_INTERVAL

# Logging sozlash
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database yaratish
db = Database()

# ============ HELPER FUNCTIONS ============

async def is_user_subscribed(bot, user_id: int) -> bool:
    """Foydalanuvchi barcha majburiy kanallarga obuna bo'lganligini tekshirish"""
    channels = db.get_all_channels()
    
    if not channels:
        return True  # Agar kanal yo'q bo'lsa, obuna shart emas
    
    for channel_id, _ in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except TelegramError as e:
            logger.error(f"Kanal tekshirishda xato {channel_id}: {e}")
            return False
    
    return True

def check_answer(user_answer: str, correct_answer: str) -> tuple:
    """Javoblarni tekshirish va to'g'ri javoblar sonini qaytarish"""
    user_answer = user_answer.lower().strip()
    correct_answer = correct_answer.lower().strip()
    
    # Uzunliklarni tenglash
    min_len = min(len(user_answer), len(correct_answer))
    correct_count = 0
    
    for i in range(min_len):
        if user_answer[i] == correct_answer[i]:
            correct_count += 1
    
    total_count = len(correct_answer)
    return correct_count, total_count

# ============ USER COMMANDS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buyrug'i"""
    user = update.effective_user
    
    # Foydalanuvchini database ga qo'shish
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_text = f"""
👋 Assalomu alaykum, {user.first_name}!

🎓 Test botiga xush kelibsiz!

📝 Test topshirish uchun quyidagi formatda javob yuboring:
<code>&lt;test raqami&gt;*abcdaa...</code>

Masalan: <code>1*abcdabcdabcd</code>

💡 Buyruqlar:
/help - Yordam
/tests - Mavjud testlar ro'yxati

⚠️ Har bir test uchun faqat 1 marta javob yuborishingiz mumkin!
"""
    
    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam buyrug'i"""
    help_text = """
📚 <b>Bot qo'llanmasi</b>

<b>Test topshirish:</b>
Test javoblarini quyidagi formatda yuboring:
<code>&lt;test raqami&gt;*abcdaa...</code>

Misol:
<code>1*abcdabcdabcd</code>
<code>5*aabbccddee</code>

<b>Javoblar:</b>
• Kichik yoki katta harflarda yozishingiz mumkin
• Har bir harf variant belgisini bildiradi (a, b, c, d, e va h.k.)
• Bir test uchun faqat 1 marta javob berishingiz mumkin

<b>Buyruqlar:</b>
/start - Botni qayta ishga tushirish
/help - Bu yordam
/tests - Mavjud testlar ro'yxati
"""
    
    if update.effective_user.id == ADMIN_ID:
        help_text += """
<b>Admin buyruqlari:</b>
/admin - Admin panel
"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def tests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavjud testlar ro'yxatini ko'rsatish"""
    tests = db.get_all_tests()
    
    if not tests:
        await update.message.reply_text("❌ Hozircha testlar mavjud emas.")
        return
    
    text = "📋 <b>Mavjud testlar:</b>\n\n"
    for test_id in tests:
        text += f"• Test #{test_id}\n"
    
    text += "\n💡 Test topshirish uchun:\n<code>&lt;test raqami&gt;*javoblar</code>"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi javobini qayta ishlash"""
    user = update.effective_user
    message_text = update.message.text.strip()
    
    # Javob formatini tekshirish: <test_id>*<answers>
    match = re.match(r'^(\d+)\*([a-zA-Z]+)$', message_text)
    
    if not match:
        return  # Format noto'g'ri bo'lsa, hech narsa qilmaymiz
    
    test_id = int(match.group(1))
    user_answer = match.group(2).lower()
    
    # Majburiy obunani tekshirish
    if not await is_user_subscribed(context.bot, user.id):
        channels = db.get_all_channels()
        text = "⚠️ Testda qatnashish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
        
        for channel_id, channel_name in channels:
            channel_link = f"https://t.me/{channel_id.replace('@', '')}"
            text += f"• {channel_name or channel_id}\n"
        
        text += "\n✅ Obuna bo'lgandan keyin qaytadan urinib ko'ring!"
        await update.message.reply_text(text)
        return
    
    # Test mavjudligini tekshirish
    correct_answer = db.get_test(test_id)
    if not correct_answer:
        await update.message.reply_text(f"❌ Test #{test_id} mavjud emas!")
        return
    
    # Foydalanuvchi oldin javob yuborgan yoki yo'qligini tekshirish
    if db.has_user_submitted(user.id, test_id):
        await update.message.reply_text(
            f"⚠️ Siz allaqachon Test #{test_id} uchun javob yuborgansiz!\n"
            "Har bir test uchun faqat 1 marta javob berishingiz mumkin."
        )
        return
    
    # Javoblarni tekshirish
    correct_count, total_count = check_answer(user_answer, correct_answer)
    
    # Natijani saqlash
    success = db.save_user_answer(
        user_id=user.id,
        test_id=test_id,
        user_answer=user_answer,
        correct_count=correct_count,
        total_count=total_count
    )
    
    if not success:
        await update.message.reply_text("❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        return
    
    # Natijani ko'rsatish
    score = (correct_count / total_count * 100) if total_count > 0 else 0
    
    result_text = f"""
✅ <b>Test #{test_id} - Natija</b>

📊 To'g'ri javoblar: {correct_count}/{total_count}
💯 Ball: {score:.1f}%

{"🎉 Ajoyib natija!" if score >= 80 else "💪 Keyingi safar yaxshiroq bo'ladi!"}
"""
    
    await update.message.reply_text(result_text, parse_mode='HTML')

# ============ ADMIN COMMANDS ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sizda admin huquqi yo'q!")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_channel")],
        [InlineKeyboardButton("➖ Kanal o'chirish", callback_data="admin_remove_channel")],
        [InlineKeyboardButton("📝 Kanallar ro'yxati", callback_data="admin_list_channels")],
        [InlineKeyboardButton("📋 Test qo'shish", callback_data="admin_add_test")],
        [InlineKeyboardButton("📊 Leaderboard", callback_data="admin_leaderboard")],
        [InlineKeyboardButton("📢 Broadcasting", callback_data="admin_broadcast")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 <b>Admin Panel</b>\n\nKerakli amalni tanlang:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin callback handler"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Sizda admin huquqi yo'q!")
        return
    
    data = query.data
    
    if data == "admin_add_channel":
        await query.edit_message_text(
            "➕ <b>Kanal qo'shish</b>\n\n"
            "Kanal ID sini yuboring (@ belgisi bilan):\n"
            "Masalan: <code>@mychannel</code>\n\n"
            "Format: <code>kanal_id kanal_nomi</code>\n"
            "Masalan: <code>@mychannel Mening Kanalom</code>",
            parse_mode='HTML'
        )
        context.user_data['waiting_for'] = 'channel_add'
    
    elif data == "admin_remove_channel":
        channels = db.get_all_channels()
        if not channels:
            await query.edit_message_text("❌ Hozircha kanallar mavjud emas.")
            return
        
        text = "➖ <b>Kanal o'chirish</b>\n\nO'chirish uchun kanal ID sini yuboring:\n\n"
        for channel_id, channel_name in channels:
            text += f"• <code>{channel_id}</code> - {channel_name or 'Nomsiz'}\n"
        
        await query.edit_message_text(text, parse_mode='HTML')
        context.user_data['waiting_for'] = 'channel_remove'
    
    elif data == "admin_list_channels":
        channels = db.get_all_channels()
        if not channels:
            await query.edit_message_text("❌ Hozircha kanallar mavjud emas.")
            return
        
        text = "📝 <b>Majburiy kanallar:</b>\n\n"
        for channel_id, channel_name in channels:
            text += f"• <code>{channel_id}</code> - {channel_name or 'Nomsiz'}\n"
        
        await query.edit_message_text(text, parse_mode='HTML')
    
    elif data == "admin_add_test":
        await query.edit_message_text(
            "📋 <b>Test qo'shish</b>\n\n"
            "To'g'ri javoblarni quyidagi formatda yuboring:\n"
            "<code>&lt;test raqami&gt;*to'g'ri_javoblar</code>\n\n"
            "Masalan: <code>1*abcdabcdabcd</code>",
            parse_mode='HTML'
        )
        context.user_data['waiting_for'] = 'test_add'
    
    elif data == "admin_leaderboard":
        tests = db.get_all_tests()
        if not tests:
            await query.edit_message_text("❌ Hozircha testlar mavjud emas.")
            return
        
        text = "📊 <b>Leaderboard</b>\n\nTest raqamini yuboring:\n\n"
        for test_id in tests:
            text += f"• Test #{test_id}\n"
        
        await query.edit_message_text(text, parse_mode='HTML')
        context.user_data['waiting_for'] = 'leaderboard_view'
    
    elif data == "admin_broadcast":
        await query.edit_message_text(
            "📢 <b>Broadcasting</b>\n\n"
            "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:",
            parse_mode='HTML'
        )
        context.user_data['waiting_for'] = 'broadcast'

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin xabarlarini qayta ishlash"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    waiting_for = context.user_data.get('waiting_for')
    
    if not waiting_for:
        return
    
    message_text = update.message.text.strip()
    
    if waiting_for == 'channel_add':
        # Format: @channel_id channel_name yoki faqat @channel_id
        parts = message_text.split(maxsplit=1)
        channel_id = parts[0]
        channel_name = parts[1] if len(parts) > 1 else None
        
        db.add_channel(channel_id, channel_name)
        await update.message.reply_text(
            f"✅ Kanal qo'shildi!\n"
            f"ID: <code>{channel_id}</code>\n"
            f"Nom: {channel_name or 'Nomsiz'}",
            parse_mode='HTML'
        )
        context.user_data.pop('waiting_for', None)
    
    elif waiting_for == 'channel_remove':
        channel_id = message_text
        db.remove_channel(channel_id)
        await update.message.reply_text(
            f"✅ Kanal o'chirildi: <code>{channel_id}</code>",
            parse_mode='HTML'
        )
        context.user_data.pop('waiting_for', None)
    
    elif waiting_for == 'test_add':
        # Format: <test_id>*<answers>
        match = re.match(r'^(\d+)\*([a-zA-Z]+)$', message_text)
        
        if not match:
            await update.message.reply_text(
                "❌ Noto'g'ri format!\n"
                "To'g'ri format: <code>&lt;test raqami&gt;*javoblar</code>\n"
                "Masalan: <code>1*abcdabcd</code>",
                parse_mode='HTML'
            )
            return
        
        test_id = int(match.group(1))
        answers = match.group(2).lower()
        
        db.add_test(test_id, answers, ADMIN_ID)
        await update.message.reply_text(
            f"✅ Test qo'shildi!\n"
            f"Test #{test_id}\n"
            f"Savollar soni: {len(answers)}",
            parse_mode='HTML'
        )
        context.user_data.pop('waiting_for', None)
    
    elif waiting_for == 'leaderboard_view':
        try:
            test_id = int(message_text)
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri test raqami!")
            return
        
        leaderboard = db.get_leaderboard(test_id, limit=10)
        
        if not leaderboard:
            await update.message.reply_text(f"❌ Test #{test_id} uchun natijalar yo'q.")
            context.user_data.pop('waiting_for', None)
            return
        
        text = f"🏆 <b>Test #{test_id} - Top 10</b>\n\n"
        
        for idx, result in enumerate(leaderboard, 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            name = result['first_name'] or result['username'] or "Nomsiz"
            score = result['score']
            correct = result['correct_count']
            total = result['total_count']
            
            text += f"{medal} {name} - {score:.1f}% ({correct}/{total})\n"
        
        await update.message.reply_text(text, parse_mode='HTML')
        context.user_data.pop('waiting_for', None)
    
    elif waiting_for == 'broadcast':
        users = db.get_all_users()
        
        success_count = 0
        fail_count = 0
        
        await update.message.reply_text(
            f"📤 Xabar yuborilmoqda...\n"
            f"Jami foydalanuvchilar: {len(users)}"
        )
        
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 <b>E'lon</b>\n\n{message_text}",
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Telegram limitga tushmaslik uchun
            except Exception as e:
                fail_count += 1
                logger.error(f"Xabar yuborishda xato {user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ Broadcasting tugadi!\n"
            f"Muvaffaqiyatli: {success_count}\n"
            f"Xatolik: {fail_count}"
        )
        context.user_data.pop('waiting_for', None)

# ============ KEEP-ALIVE MECHANISM ============

async def health_check(request):
    """Health check endpoint"""
    return web.Response(text="OK")

async def start_web_server():
    """Aiohttp web server ishga tushirish"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Web server started on port {PORT}")

async def keep_alive_ping():
    """O'zini o'zi ping qilish (Render uchun)"""
    if not SELF_URL:
        logger.warning("SELF_URL o'rnatilmagan, keep-alive ishlamaydi")
        return
    
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SELF_URL}/health") as response:
                    logger.info(f"Keep-alive ping: {response.status}")
        except Exception as e:
            logger.error(f"Keep-alive ping xatosi: {e}")

# ============ MAIN ============

async def main():
    """Asosiy funksiya"""
    # Application yaratish
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tests", tests_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # Message handlerlar (tartib muhim!)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),
        admin_message_handler
    ))
    application.add_handler(MessageHandler(
        filters.Regex(r'^\d+\*[a-zA-Z]+$'),
        handle_answer
    ))
    
    # Web server va keep-alive boshlash
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive_ping())
    
    # Botni ishga tushirish (polling)
    logger.info("Bot ishga tushmoqda...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    asyncio.run(main())
