import re
from typing import Optional
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
    # Check if this command is run in a Group or Supergroup chat
    if message.chat.type in ["group", "supergroup"]:
        # Setup match directly in the group, bypassing channel select & user admin checks
        await state.update_data(
            channel_id=message.chat.id,
            channel_title=message.chat.title,
            is_group_match=True
        )
        await state.set_state(AdminStates.waiting_for_category)
        await message.reply(
            "🎮 <b>بدء مباراة Mythikra جديدة في هذه المجموعة!</b>\n\n"
            "🏷️ يرجى كتابة <b>تصنيف المباراة</b> الآن كرسالة نصية مباشرة (مثال: <code>الحيوانات</code>، <code>الدول</code>، <code>كرة القدم</code>):",
            parse_mode="HTML"
        )
        return

    # If run in Private Chat
    await state.set_state(AdminStates.waiting_for_channel)
    
    # Load previously saved channels
    saved_channels = registry.load_saved_channels()
    
    text = (
        "📢 <b>إنشاء مباراة جديدة:</b>\n\n"
        "يرجى إرسال معرف القناة المستهدفة، أو رابطها الكامل، أو قم <b>بتحويل (Forward)</b> أي رسالة من تلك القناة إلى هنا مباشرة.\n\n"
    )
    
    if saved_channels:
        builder = InlineKeyboardBuilder()
        for cid, ctitle in saved_channels.items():
            builder.button(text=f"📢 {ctitle}", callback_data=f"select_channel:{cid}")
        builder.adjust(1)
        
        text += "💡 <b>أو اختر إحدى القنوات المستخدمة سابقاً من الأزرار أدناه:</b>"
        await message.reply(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        text += (
            "<b>أمثلة للمدخلات المقبولة:</b>\n"
            "• معرف عادي: <code>@mythikra</code>\n"
            "• رابط عام: <code>https://t.me/mythikra</code>\n"
            "• رابط خاص: <code>https://t.me/c/1234567890/12</code>\n"
            "• تحويل رسالة مباشرة من القناة للبوت.\n\n"
            "<i>ملاحظة: سيتحقق البوت تلقائياً من أنك مشرف أو مالك في القناة المحددة للسماح لك ببدء اللعب.</i>"
        )
        await message.reply(text, parse_mode="HTML")

@router.callback_query(AdminStates.waiting_for_channel, F.data.startswith("select_channel:"))
async def handle_select_saved_channel(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    try:
        chat = await callback.bot.get_chat(channel_id)
        
        # Verify bot permissions
        bot_member = await callback.bot.get_chat_member(chat.id, callback.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await callback.answer("⚠️ لست مشرفاً في هذه القناة حالياً!", show_alert=True)
            return
            
        # Verify user permissions
        user_member = await callback.bot.get_chat_member(chat.id, callback.from_user.id)
        if user_member.status not in ["administrator", "creator"]:
            await callback.answer("⚠️ يجب أن تكون مشرفاً في القناة المحددة لبدء مباراة فيها!", show_alert=True)
            return
            
        await state.update_data(channel_id=chat.id, channel_title=chat.title, is_group_match=False)
        await state.set_state(AdminStates.waiting_for_category)
        
        await callback.message.edit_text(
            f"✅ تم تحديد القناة: <b>{chat.title}</b>\n\n"
            f"🏷️ يرجى كتابة <b>تصنيف المباراة</b> وإرساله الآن كرسالة نصية مباشرة:",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"⚠️ فشل التحقق من القناة المحفوظة: {str(e)}", show_alert=True)

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
        await state.update_data(channel_id=chat.id, channel_title=chat.title, is_group_match=False)
        
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
    
    await state.update_data(category=category)
    
    # Prompt for questions limit
    builder = InlineKeyboardBuilder()
    builder.button(text="♾️ بلا حدود", callback_data="limit_questions:unlimited")
    
    await state.set_state(AdminStates.waiting_for_questions_limit)
    await message.reply(
        "❓ <b>تحديد حد الأسئلة لكل لاعب:</b>\n\n"
        "يرجى كتابة عدد الأسئلة الأقصى المسموح به لكل لاعب كعدد رقمي (مثال: <code>15</code>)، أو اضغط على الزر أدناه لتكون الأسئلة بلا حدود:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# Questions Limit handlers
@router.callback_query(AdminStates.waiting_for_questions_limit, F.data == "limit_questions:unlimited")
async def process_questions_unlimited(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(max_questions=None)
    await ask_guesses_limit(callback.message, state)
    await callback.answer()

@router.message(AdminStates.waiting_for_questions_limit)
async def process_questions_number(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.reply("⚠️ يرجى إدخال عدد رقمي صحيح أكبر من صفر أو الضغط على زر (بلا حدود):")
        return
        
    await state.update_data(max_questions=int(text))
    await ask_guesses_limit(message, state)

async def ask_guesses_limit(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="♾️ بلا حدود", callback_data="limit_guesses:unlimited")
    
    await state.set_state(AdminStates.waiting_for_guesses_limit)
    await message.reply(
        "🎯 <b>تحديد حد التخمينات لكل لاعب:</b>\n\n"
        "يرجى كتابة عدد التخمينات الأقصى المسموح به لكل لاعب كعدد رقمي (مثال: <code>3</code>)، أو اضغط على الزر أدناه لتكون التخمينات بلا حدود:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# Guesses Limit handlers
@router.callback_query(AdminStates.waiting_for_guesses_limit, F.data == "limit_guesses:unlimited")
async def process_guesses_unlimited(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(max_guesses=None)
    data = await state.get_data()
    await setup_match(callback.message, state, data)
    await callback.answer()

@router.message(AdminStates.waiting_for_guesses_limit)
async def process_guesses_number(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.reply("⚠️ يرجى إدخال عدد رقمي صحيح أكبر من صفر أو الضغط على زر (بلا حدود):")
        return
        
    await state.update_data(max_guesses=int(text))
    data = await state.get_data()
    await setup_match(message, state, data)

async def setup_match(message: types.Message, state: FSMContext, data: dict):
    channel_id = data.get("channel_id")
    channel_title = data.get("channel_title")
    category = data.get("category")
    max_questions = data.get("max_questions")
    max_guesses = data.get("max_guesses")
    is_group_match = data.get("is_group_match", False)
    creator_id = message.chat.id
    
    # Reset FSM state
    await state.clear()
    
    # Create the match in registry
    match = registry.create_match(channel_id, channel_title, category, creator_id)
    match.max_questions = max_questions
    match.max_guesses = max_guesses
    match.is_group_match = is_group_match
    
    # Save channel if it is a channel match (for future quick selection)
    if not is_group_match:
        registry.save_channel(channel_id, channel_title)
    
    # Create join button
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 انضمام", callback_data=f"join_match:{match.match_id}")
    
    match.state = MatchState.JOINING
    
    # Fetch bot username dynamically
    bot_info = await message.bot.get_me()
    msg_text = match.format_match_message(bot_info.username)
    
    try:
        # Post join message to channel or group directly
        channel_msg = await message.bot.send_message(
            chat_id=channel_id,
            text=msg_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        match.channel_message_id = channel_msg.message_id
        
        q_limit_str = f"<b>{max_questions}</b>" if max_questions is not None else "<i>بلا حدود</i>"
        g_limit_str = f"<b>{max_guesses}</b>" if max_guesses is not None else "<i>بلا حدود</i>"
        
        if is_group_match:
            await message.reply(
                f"✅ <b>بدأت مرحلة الانضمام داخل هذه المجموعة!</b>\n"
                f"🏷️ التصنيف: <b>{category}</b>\n"
                f"❓ حد الأسئلة: {q_limit_str}\n"
                f"🎯 حد التخمينات: {g_limit_str}\n\n"
                f"بانتظار انضمام لاعبين اثنين...",
                parse_mode="HTML"
            )
        else:
            await message.bot.send_message(
                chat_id=creator_id,
                text=f"✅ تم إنشاء المباراة بنجاح ونشر رسالة الانضمام في القناة <b>{channel_title}</b>!\n"
                     f"🏷️ التصنيف: <b>{category}</b>\n"
                     f"❓ حد الأسئلة: {q_limit_str}\n"
                     f"🎯 حد التخمينات: {g_limit_str}\n\n"
                     f"بانتظار انضمام لاعبين اثنين...",
                parse_mode="HTML"
            )
    except Exception as e:
        registry.remove_match(match.match_id)
        reply_to_id = creator_id if not is_group_match else channel_id
        await message.bot.send_message(
            chat_id=reply_to_id,
            text=f"⚠️ فشل نشر رسالة المباراة. تأكد من صلاحية إرسال الرسائل للبوت.\n\n"
                 f"تفاصيل الخطأ: <code>{str(e)}</code>",
            parse_mode="HTML"
        )

# Cancel Match Command
@router.message(Command("cancelmatch"))
async def cmd_cancelmatch(message: types.Message):
    # If in group, check if there's a match in this group, and let anyone cancel (or check creator/admin)
    if message.chat.type in ["group", "supergroup"]:
        match = registry.get_match_by_channel(message.chat.id)
        if not match:
            await message.reply("ℹ️ لا توجد مباراة نشطة في هذه المجموعة حالياً.")
            return
            
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ إلغاء المباراة جارية", callback_data=f"cancel_match:{match.match_id}")
        await message.reply("🛡️ هل أنت متأكد من إلغاء المباراة الحالية؟", reply_markup=builder.as_markup())
        return

    # If in private
    my_matches = []
    for m in registry.active_matches.values():
        try:
            # For group matches, creator of match is the creator_id
            if m.is_group_match:
                if m.creator_id == message.chat.id:
                    my_matches.append(m)
            else:
                member = await message.bot.get_chat_member(m.channel_id, message.from_user.id)
                if member.status in ["administrator", "creator"]:
                    my_matches.append(m)
        except Exception:
            pass
            
    if not my_matches:
        await message.reply("ℹ️ لا توجد مباريات نشطة قمت بإنشائها أو تملك صلاحية إدارتها حالياً.")
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
        
    # Verify cancellation permissions
    if not match.is_group_match:
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
            
    # Delete the channel/group message
    try:
        await callback.bot.delete_message(chat_id=match.channel_id, message_id=match.channel_message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")
        
    # Post cancellation notification in channel/group
    try:
        await callback.bot.send_message(
            chat_id=match.channel_id,
            text=f"🛑 <b>مباراة لغز التخمين (التصنيف: {match.category}) تم إلغاؤها.</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error writing cancellation message: {e}")
        
    registry.remove_match(match_id)
    await callback.answer("✅ تم إلغاء المباراة وحذفها بنجاح.", show_alert=True)
    if callback.message.chat.type == "private":
        await callback.message.edit_text("✅ تم إلغاء المباراة بنجاح وتنبيه اللاعبين.")
    else:
        await callback.message.delete()
