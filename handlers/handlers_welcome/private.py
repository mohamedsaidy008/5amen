from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from states import WelcomeStates
from handlers_welcome.channel import load_welcome_settings, save_welcome_settings

router = Router()

async def check_subscription(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=config.REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Subscription check error for {user_id}: {e}")
        return False

def get_settings_keyboard(settings: dict):
    builder = InlineKeyboardBuilder()
    
    welcome_status = "🟢 مفعل" if settings.get("welcome_enabled", True) else "🔴 معطل"
    ban_status = "🟢 مفعل" if settings.get("ban_on_leave_enabled", True) else "🔴 معطل"
    
    builder.button(text=f"👥 الترحيب: {welcome_status}", callback_data="welcome_action:toggle_welcome")
    builder.button(text=f"🚫 الحظر عند الخروج: {ban_status}", callback_data="welcome_action:toggle_ban")
    builder.button(text="📝 تعديل نص الترحيب", callback_data="welcome_action:edit_text")
    builder.button(text="🔓 إدارة المحظورين", callback_data="welcome_action:unban_list")
    builder.adjust(1)
    
    return builder.as_markup()

def get_settings_text(settings: dict) -> str:
    welcome_text = settings.get("welcome_text", "مرحباً بك يا {name} نورتنا القناة قناتك لا عاد تطلع 🌹")
    welcome_status_text = "مفعل" if settings.get("welcome_enabled", True) else "معطل"
    ban_status_text = "مفعل" if settings.get("ban_on_leave_enabled", True) else "معطل"
    
    return (
        "⚙️ <b>لوحة تحكم إعدادات الترحيب والحظر التلقائي:</b>\n\n"
        f"👥 <b>نظام الترحيب:</b> {welcome_status_text}\n"
        f"🚫 <b>الحظر عند المغادرة:</b> {ban_status_text}\n\n"
        f"📝 <b>نص الترحيب الحالي:</b>\n"
        f"<code>{welcome_text}</code>"
    )

@router.message(Command("start"))
async def welcome_start(message: types.Message):
    # Subscription Check to REQUIRED_CHANNEL (@mythikra)
    subscribed = await check_subscription(message.bot, message.from_user.id)
    if not subscribed:
        builder = InlineKeyboardBuilder()
        channel_username = config.REQUIRED_CHANNEL.replace("@", "")
        builder.button(text="📢 الاشتراك في القناة الرئيسية", url=f"https://t.me/{channel_username}")
        await message.reply(
            f"⚠️ <b>عذراً! لا يمكنك استخدام البوت أو التحكم بإعداداته قبل الاشتراك في القناة الرئيسية.</b>\n\n"
            f"يرجى الاشتراك في القناة: {config.REQUIRED_CHANNEL} أولاً، ثم عُد وأرسل /start مجدداً.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    settings = load_welcome_settings()
    await message.reply(
        get_settings_text(settings),
        reply_markup=get_settings_keyboard(settings),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("welcome_action:"))
async def process_welcome_actions(callback: types.CallbackQuery, state: FSMContext):
    # Subscription Check
    subscribed = await check_subscription(callback.bot, callback.from_user.id)
    if not subscribed:
        await callback.answer(f"⚠️ يجب عليك الاشتراك في القناة {config.REQUIRED_CHANNEL} أولاً!", show_alert=True)
        return

    action = callback.data.split(":")[1]
    settings = load_welcome_settings()
    
    if action == "toggle_welcome":
        settings["welcome_enabled"] = not settings.get("welcome_enabled", True)
        save_welcome_settings(settings)
        await callback.message.edit_text(
            get_settings_text(settings),
            reply_markup=get_settings_keyboard(settings),
            parse_mode="HTML"
        )
        await callback.answer("✅ تم تعديل حالة الترحيب")
        
    elif action == "toggle_ban":
        settings["ban_on_leave_enabled"] = not settings.get("ban_on_leave_enabled", True)
        save_welcome_settings(settings)
        await callback.message.edit_text(
            get_settings_text(settings),
            reply_markup=get_settings_keyboard(settings),
            parse_mode="HTML"
        )
        await callback.answer("✅ تم تعديل حالة الحظر التلقائي")
        
    elif action == "edit_text":
        await state.set_state(WelcomeStates.waiting_for_welcome_text)
        await callback.message.answer(
            "📝 <b>يرجى إرسال نص الترحيب الجديد الآن:</b>\n\n"
            "💡 يمكنك استخدام الرموز التالية ليتم استبدالها تلقائياً:\n"
            "• <code>{name}</code> - اسم العضو الجديد كاملاً.\n"
            "• <code>{username}</code> - يوزر نيم العضو الجديد (إن وجد، وإلا سيتم عرض الاسم).\n\n"
            "مثال: <code>مرحباً بك يا {name} نورت القناة 🌹</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        
    elif action == "unban_list":
        await display_unban_list(callback.message)
        await callback.answer()

@router.message(WelcomeStates.waiting_for_welcome_text)
async def process_new_welcome_text(message: types.Message, state: FSMContext):
    subscribed = await check_subscription(message.bot, message.from_user.id)
    if not subscribed:
        await message.reply(f"⚠️ يجب عليك الاشتراك في القناة {config.REQUIRED_CHANNEL} أولاً!")
        return

    new_text = message.text.strip()
    if not new_text:
        await message.reply("⚠️ يرجى إرسال نص ترحيب صالح:")
        return
        
    settings = load_welcome_settings()
    settings["welcome_text"] = new_text
    save_welcome_settings(settings)
    await state.clear()
    
    await message.reply("✅ تم حفظ نص الترحيب الجديد بنجاح!")
    
    # Re-display main menu
    await message.answer(
        get_settings_text(settings),
        reply_markup=get_settings_keyboard(settings),
        parse_mode="HTML"
    )

async def display_unban_list(message: types.Message):
    settings = load_welcome_settings()
    banned_users = settings.get("banned_users", {})
    
    if not banned_users:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 العودة للإعدادات", callback_data="welcome_back_settings")
        await message.answer("ℹ️ لا يوجد مستخدمين محظورين من قبل البوت حالياً.", reply_markup=builder.as_markup())
        return
        
    builder = InlineKeyboardBuilder()
    text = "🔓 <b>قائمة المستخدمين المحظورين (اضغط لإلغاء الحظر):</b>\n\n"
    
    for uid, details in banned_users.items():
        name = details.get("name", f"User {uid}")
        chat_title = details.get("chat_title", "القناة")
        text += f"• {name} (غادر {chat_title})\n"
        builder.button(text=f"🔓 إلغاء حظر: {name}", callback_data=f"unban_user:{uid}")
        
    builder.button(text="🔙 العودة للإعدادات", callback_data="welcome_back_settings")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "welcome_back_settings")
async def handle_back_settings(callback: types.CallbackQuery):
    settings = load_welcome_settings()
    await callback.message.edit_text(
        get_settings_text(settings),
        reply_markup=get_settings_keyboard(settings),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("unban_user:"))
async def handle_unban_user(callback: types.CallbackQuery):
    user_id = callback.data.split(":")[1]
    settings = load_welcome_settings()
    banned_users = settings.get("banned_users", {})
    
    if user_id not in banned_users:
        await callback.answer("⚠️ المستخدم غير موجود في قائمة الحظر الخاصة بالبوت.", show_alert=True)
        return
        
    details = banned_users[user_id]
    chat_id = details.get("chat_id")
    name = details.get("name", "المستخدم")
    chat_title = details.get("chat_title", "القناة")
    
    try:
        # Unban user from the chat
        await callback.bot.unban_chat_member(chat_id=chat_id, user_id=int(user_id))
        
        # Remove from settings
        del banned_users[user_id]
        save_welcome_settings(settings)
        
        await callback.answer(f"✅ تم إلغاء حظر {name} بنجاح!", show_alert=True)
        
        # Refresh the list
        await callback.message.delete()
        await display_unban_list(callback.message)
    except Exception as e:
        await callback.answer(
            f"⚠️ فشل إلغاء الحظر.\n\n"
            f"تأكد من أن البوت لا يزال مشرفاً في القناة/المجموعة: {chat_title}.\n"
            f"تفاصيل الخطأ: {str(e)}",
            show_alert=True
        )
