import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from states import AdminStates
from models import registry, MatchState, Match

router = Router()

@router.message(Command("newmatch"))
async def cmd_newmatch(message: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_channel)
    await message.reply(
        "📢 <b>إنشاء مباراة جديدة:</b>\n\n"
        "يرجى إرسال معرف القناة المستهدفة، أو رابطها الكامل، أو قم <b>بتحويل (Forward)</b> أي رسالة من تلك القناة إلى هنا مباشرة.\n\n"
        "<b>أمثلة للمدخلات المقبولة:</b>\n"
        "• معرف عادي: <code>@mythikra</code>\n"
        "• رابط عام: <code>https://t.me/mythikra</code>\n"
        "• رابط خاص: <code>https://t.me/c/1234567890/12</code>\n"
        "• تحويل رسالة مباشرة من القناة للبوت.\n\n"
        "<i>ملاحظة: سيتحقق البوت تلقائياً من أنك مشرف أو مالك في القناة المحددة للسماح لك ببدء اللعب.</i>",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_channel)
async def process_channel(message: types.Message, state: FSMContext):
    channel_input = None
    
    # 1. Check if the message is forwarded from a channel
    if message.forward_from_chat:
        if message.forward_from_chat.type == "channel":
            channel_input = str(message.forward_from_chat.id)
            
    # 2. Parse text input (if not forwarded)
    if not channel_input:
        text = message.text.strip() if message.text else ""
        if not text:
            await message.reply("⚠️ يرجى إرسال معرف القناة، رابطها، أو قم بتحويل رسالة منها:")
            return
            
        # Parse public links: t.me/username or https://t.me/username
        public_match = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,})', text)
        if public_match:
            username = public_match.group(1)
            if username.lower() != 'c':
                channel_input = "@" + username
                
        # Parse private links: https://t.me/c/123456789/456
        if not channel_input:
            private_match = re.search(r'(?:https?://)?(?:t\.me|telegram\.me)/c/(\d+)', text)
            if private_match:
                channel_input = f"-100{private_match.group(1)}"
                
        # If it's a standard text input (username or ID)
        if not channel_input:
            if text.startswith("-") or text.startswith("@"):
                channel_input = text
            elif text.isdigit():
                channel_input = f"-100{text}"
            else:
                channel_input = "@" + text
                
    try:
        # Check if bot is in the channel and is admin
        chat = await message.bot.get_chat(channel_input)
        if chat.type != "channel":
            await message.reply("⚠️ هذا المعرف لا يعود لقناة. يرجى إرسال معرف قناة صحيح:")
            return
            
        bot_member = await message.bot.get_chat_member(chat.id, message.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await message.reply("⚠️ لست مشرفاً في هذه القناة. يرجى ترقيتي لمشرف وتفعيل صلاحية إرسال الرسائل، ثم أرسل المعرف مجدداً:")
            return
            
        # Check if the user who sent /newmatch is an admin/creator in the target channel
        user_member = await message.bot.get_chat_member(chat.id, message.from_user.id)
        if user_member.status not in ["administrator", "creator"]:
            await message.reply(
                "⚠️ <b>صلاحيات غير كافية:</b>\n"
                "يجب أن تكون مشرفاً أو مالكاً في القناة التي حددتها لتتمكن من إنشاء مباراة فيها.\n\n"
                "يرجى إرسال معرف قناة تديرها وتكون مشرفاً فيها:",
                parse_mode="HTML"
            )
            return
            
        # Store in FSM
        await state.update_data(channel_id=chat.id, channel_title=chat.title)
        
        await state.set_state(AdminStates.waiting_for_category)
        await message.reply(
            f"✅ تم التحقق من القناة وصلاحياتك: <b>{chat.title}</b>\n\n"
            f"🏷️ يرجى كتابة <b>تصنيف المباراة</b> وإرساله الآن كرسالة نصية مباشرة (مثال: <code>الحيوانات</code>، <code>الدول</code>، <code>كرة القدم</code>):",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await message.reply(
            f"⚠️ لم أتمكن من العثور على القناة أو التحقق منها.\n"
            f"تأكد من صحة الرابط/المعرف ومن أنني مضاف في القناة كمشرف.\n\n"
            f"تفاصيل الخطأ: <code>{str(e)}</code>\n"
            f"يرجى إعادة المحاولة وإرسال المعرف الصحيح:",
            parse_mode="HTML"
        )

@router.message(AdminStates.waiting_for_category)
async def process_category_text(message: types.Message, state: FSMContext):
    category = message.text.strip()
    if not category:
        await message.reply("⚠️ الرجاء كتابة اسم تصنيف صالح:")
        return
    await setup_match(message, state, category)

async def setup_match(message: types.Message, state: FSMContext, category: str):
    data = await state.get_data()
    channel_id = data.get("channel_id")
    channel_title = data.get("channel_title")
    creator_id = message.chat.id # admin who initiated it
    
    # Reset FSM state for the admin
    await state.clear()
    
    # Create the match in registry
    match = registry.create_match(channel_id, channel_title, category, creator_id)
    
    # Create join button
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 انضمام", callback_data=f"join_match:{match.match_id}")
    
    match.state = MatchState.JOINING
    
    # Fetch bot username dynamically
    bot_info = await message.bot.get_me()
    msg_text = match.format_match_message(bot_info.username)
    
    try:
        # Post join message to channel
        channel_msg = await message.bot.send_message(
            chat_id=channel_id,
            text=msg_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        match.channel_message_id = channel_msg.message_id
        
        await message.bot.send_message(
            chat_id=creator_id,
            text=f"✅ تم إنشاء المباراة بنجاح ونشر رسالة الانضمام في القناة <b>{channel_title}</b>!\n"
                 f"🏷️ التصنيف المختار: <b>{category}</b>\n\n"
                 f"بانتظار انضمام لاعبين اثنين...",
            parse_mode="HTML"
        )
    except Exception as e:
        registry.remove_match(match.match_id)
        await message.bot.send_message(
            chat_id=creator_id,
            text=f"⚠️ فشل نشر رسالة المباراة في القناة. تأكد من صلاحية إرسال الرسائل للبوت.\n\n"
                 f"تفاصيل الخطأ: <code>{str(e)}</code>",
            parse_mode="HTML"
        )

# Cancel Match Command
@router.message(Command("cancelmatch"))
async def cmd_cancelmatch(message: types.Message):
    # Find active matches where the user is an admin of the match's channel
    my_matches = []
    for m in registry.active_matches.values():
        try:
            member = await message.bot.get_chat_member(m.channel_id, message.from_user.id)
            if member.status in ["administrator", "creator"]:
                my_matches.append(m)
        except Exception:
            pass
            
    if not my_matches:
        await message.reply("ℹ️ لا توجد مباريات نشطة في قنوات تكون مشرفاً فيها حالياً.")
        return
        
    builder = InlineKeyboardBuilder()
    for m in my_matches:
        builder.button(text=f"❌ {m.channel_title} ({m.category})", callback_data=f"cancel_match:{m.match_id}")
    builder.adjust(1)
    
    await message.reply("🛡️ اختر المباراة التي ترغب في إلغائها فوراً:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("cancel_match:"))
async def handle_cancel_match(callback: types.CallbackQuery, state: FSMContext):
    match_id = callback.data.split(":")[1]
    match = registry.get_match_by_id(match_id)
    if not match:
        await callback.answer("⚠️ المباراة غير موجودة أو انتهت بالفعل.", show_alert=True)
        return
        
    # Check if the clicking user is admin/creator in the target channel
    try:
        user_member = await callback.bot.get_chat_member(match.channel_id, callback.from_user.id)
        if user_member.status not in ["administrator", "creator"]:
            await callback.answer("⚠️ ليس لديك صلاحية إلغاء هذه المباراة (يجب أن تكون مشرفاً في القناة).", show_alert=True)
            return
    except Exception:
        await callback.answer("⚠️ فشل التحقق من صلاحيات الإشراف الخاصة بك.", show_alert=True)
        return
        
    # Notify players
    for p in match.players:
        try:
            await callback.bot.send_message(
                chat_id=p.user_id,
                text="⚠️ <b>تم إيقاف وإلغاء المباراة الحالية من قبل المدير.</b>",
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode="HTML"
            )
            # Clear player state using the base StorageKey
            state_context = FSMContext(
                storage=state.storage,
                key=StorageKey(
                    bot_id=callback.bot.id,
                    chat_id=p.user_id,
                    user_id=p.user_id
                )
            )
            await state_context.clear()
        except Exception as e:
            print(f"Error notifying player: {e}")
            
    # Delete the channel message
    try:
        await callback.bot.delete_message(chat_id=match.channel_id, message_id=match.channel_message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")
        
    # Post cancellation notification in channel
    try:
        await callback.bot.send_message(
            chat_id=match.channel_id,
            text=f"🛑 <b>مباراة لغز التخمين (التصنيف: {match.category}) تم إلغاؤها من قبل المدير.</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error writing to channel: {e}")
        
    # Remove match from registry
    registry.remove_match(match_id)
    
    await callback.answer("✅ تم إلغاء المباراة وحذفها بنجاح.", show_alert=True)
    await callback.message.edit_text("✅ تم إلغاء المباراة بنجاح وتنبيه اللاعبين.")
