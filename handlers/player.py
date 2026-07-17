from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from states import PlayerStates
from models import registry, MatchState, Match, Player
from typing import Optional

router = Router()

# Helper to check channel subscription
async def check_subscription(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=config.REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Subscription check error for {user_id}: {e}")
        return False

# Helper to check if a player has any active moves left
def has_actions_left(player: Player, match: Match) -> bool:
    has_q = match.max_questions is None or player.questions_count < match.max_questions
    has_g = match.max_guesses is None or player.guesses_count < match.max_guesses
    return has_q or has_g

# Helper to generate the player's turn keyboard based on limits
def get_turn_keyboard(player: Player, match: Match):
    builder = InlineKeyboardBuilder()
    
    show_ask = match.max_questions is None or player.questions_count < match.max_questions
    show_guess = match.max_guesses is None or player.guesses_count < match.max_guesses
    
    if show_ask:
        builder.button(text="❓ طرح سؤال", callback_data="turn_action:ask")
    if show_guess:
        builder.button(text="🎯 إعلان تخمين", callback_data="turn_action:guess")
        
    builder.button(text="🚪 انسحاب", callback_data="turn_action:withdraw")
    
    buttons_count = (1 if show_ask else 0) + (1 if show_guess else 0) + 1
    builder.adjust(2 if buttons_count >= 2 else 1)
    
    return builder.as_markup(), show_ask, show_guess

# Game loop organizer to start/continue player turn
async def start_player_turn(bot, storage, match: Match):
    p = match.get_current_player()
    opponent = match.get_opponent(p.user_id)
    bot_info = await bot.get_me()
    
    # 1. Check if the current player has any moves left
    if not has_actions_left(p, match):
        # Check if the opponent also has no moves left
        if not has_actions_left(opponent, match):
            # Both out of moves -> DRAW!
            await end_match(bot, storage, match, winner=None, loser=None, reason="draw")
            return
            
        # Only current player is out of moves -> Skip their turn
        try:
            await bot.send_message(
                chat_id=p.user_id,
                text="⚠️ <b>لقد استنفدت جميع أسئلتك وتخميناتك المتاحة في هذه المباراة!</b>\n"
                     "تم تخطي دورك تلقائياً ونقل الدور إلى خصمك.",
                parse_mode="HTML"
            )
        except Exception:
            pass
            
        # Switch turn
        match.switch_turn()
        
        # Update channel message to reflect turn change
        try:
            await bot.edit_message_text(
                chat_id=match.channel_id,
                message_id=match.channel_message_id,
                text=match.format_match_message(bot_info.username),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error editing message on turn skip: {e}")
            
        # Recurse to trigger turn for opponent
        await start_player_turn(bot, storage, match)
        return
        
    # 2. Trigger standard turn selection
    markup, _, _ = get_turn_keyboard(p, match)
    try:
        await bot.send_message(
            chat_id=p.user_id,
            text="🔔 <b>إنه دورك الآن!</b> يرجى اختيار إجراءك:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=opponent.user_id,
            text=f"⏳ إنه دور خصمك الآن (<b>{p.full_name}</b>). بانتظار خطوته.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error sending turn notifications: {e}")

# Player Joins Match from Channel
@router.callback_query(F.data.startswith("join_match:"))
async def handle_join_match(callback: types.CallbackQuery, state: FSMContext):
    match_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    username = callback.from_user.username
    
    # Get bot info dynamically
    bot_info = await callback.bot.get_me()
    
    # 1. Check if user is already in a match
    existing_match = registry.get_match_by_user(user_id)
    if existing_match:
        await callback.answer("⚠️ أنت بالفعل تشارك في مباراة أخرى حالياً!", show_alert=True)
        return
        
    # 2. Check channel subscription
    subscribed = await check_subscription(callback.bot, user_id)
    if not subscribed:
        # Show inline alert
        await callback.answer("⚠️ لا يمكنك الانضمام قبل الاشتراك في قناة صاحب البوت.", show_alert=True)
        
        # Try to send a private message with a link to subscribe
        try:
            builder = InlineKeyboardBuilder()
            channel_username = config.REQUIRED_CHANNEL.replace("@", "")
            builder.button(text="📢 الاشتراك في قناة Mythikra", url=f"https://t.me/{channel_username}")
            
            await callback.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ <b>عذراً! لا يمكنك الانضمام للمباراة قبل الاشتراك في قناة صاحب البوت.</b>\n\n"
                     f"يرجى الاشتراك في القناة: {config.REQUIRED_CHANNEL} أولاً، ثم عُد واضغط على زر الانضمام مجدداً.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception:
            # If the user hasn't started the bot, they must start it first.
            await callback.answer(
                f"⚠️ يجب الاشتراك في قناة {config.REQUIRED_CHANNEL}\n"
                f"ثم الانتقال إلى معرف البوت: @{bot_info.username} والضغط على (ابدأ / start) أولاً لتتمكن من اللعب!",
                show_alert=True
            )
        return
        
    # 3. Verify match exists and is open
    match = registry.get_match_by_id(match_id)
    if not match:
        await callback.answer("⚠️ لم يتم العثور على المباراة أو تم إلغاؤها.", show_alert=True)
        return
        
    if match.state != MatchState.JOINING or len(match.players) >= 2:
        await callback.answer("⚠️ عذراً، اكتمل عدد اللاعبين أو انتهت فترة الانضمام.", show_alert=True)
        return

    # 4. Verify if the user has started the bot in private.
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"🎮 <b>تم انضمامك لمباراة Mythikra بنجاح!</b>\n"
                 f"🏷️ التصنيف: <b>{match.category}</b>\n\n"
                 f"⏳ بانتظار انضمام اللاعب الثاني لبدء المباراة...",
            parse_mode="HTML"
        )
    except Exception as e:
        # Failed to send message because the user has not clicked /start in private chat
        await callback.answer(
            f"⚠️ يجب عليك بدء محادثة مع البوت في الخاص أولاً لتتمكن من الانضمام للعب!\n\n"
            f"يرجى الضغط هنا: @{bot_info.username} والضغط على (ابدأ / start)، ثم عُد إلى هنا واضغط (انضمام) مجدداً.",
            show_alert=True
        )
        return
        
    # 5. Add player to match in registry
    success = registry.add_player_to_match(match_id, user_id, full_name, username)
    if not success:
        await callback.answer("⚠️ فشل الانضمام للمباراة (ربما اكتملت الآن).", show_alert=True)
        return
        
    await callback.answer("✅ تم انضمامك بنجاح!")

    # Update channel message
    if len(match.players) == 1:
        try:
            builder = InlineKeyboardBuilder()
            builder.button(text="🎮 انضمام", callback_data=f"join_match:{match.match_id}")
            await callback.bot.edit_message_text(
                chat_id=match.channel_id,
                message_id=match.channel_message_id,
                text=match.format_match_message(bot_info.username),
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error editing join message: {e}")
            
    elif len(match.players) == 2:
        # Match is now full, move to CHOOSING_WORDS
        match.state = MatchState.CHOOSING_WORDS
        
        try:
            # Edit channel message to remove the join button
            await callback.bot.edit_message_text(
                chat_id=match.channel_id,
                message_id=match.channel_message_id,
                text=match.format_match_message(bot_info.username),
                reply_markup=None,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error editing join message (full): {e}")
            
        # Notify both players to input their secret words
        for p in match.players:
            try:
                # Set FSM state for each player to type their word using state.storage & StorageKey
                p_state = FSMContext(
                    storage=state.storage,
                    key=StorageKey(
                        bot_id=callback.bot.id,
                        chat_id=p.user_id,
                        user_id=p.user_id
                    )
                )
                await p_state.set_state(PlayerStates.choosing_word)
                
                await callback.bot.send_message(
                    chat_id=p.user_id,
                    text=f"🏁 <b>اكتمل اللاعبون! بدأت مرحلة اختيار الكلمات.</b>\n\n"
                         f"يرجى كتابة الشيء أو الكلمة السرية التي ستفكر فيها في هذه المباراة.\n"
                         f"⚠️ <b>الشرط:</b> يجب أن تكون الكلمة سرية وتنتمي للتصنيف: <b>{match.category}</b>.",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Error starting word choice for player {p.user_id}: {e}")

# Player inputs secret word
@router.message(PlayerStates.choosing_word)
async def process_secret_word(message: types.Message, state: FSMContext):
    word = message.text.strip()
    user_id = message.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match:
        await state.clear()
        await message.reply("⚠️ لم يتم العثور على مباراة نشطة لك حالياً.")
        return
        
    player = match.get_player_by_id(user_id)
    if not player:
        await state.clear()
        await message.reply("⚠️ حدث خطأ، لم نجد بياناتك في هذه المباراة.")
        return
        
    # Save the word
    player.secret_word = word
    player.word_approved = True  # Automatically approved
    await state.clear()
    
    # Check if both players have submitted words
    all_submitted = all(p.secret_word is not None for p in match.players)
    
    # Get bot info dynamically
    bot_info = await message.bot.get_me()
    
    if all_submitted and len(match.players) == 2:
        # Move match straight to PLAYING
        match.state = MatchState.PLAYING
        match.turn_index = 0 # Player 1's turn
        
        # Update channel message to playing status
        try:
            await message.bot.edit_message_text(
                chat_id=match.channel_id,
                message_id=match.channel_message_id,
                text=match.format_match_message(bot_info.username),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error editing message: {e}")
            
        # Notify players and start the first turn dynamically
        await start_player_turn(message.bot, state.storage, match)
            
    else:
        # Only one submitted, notify this player and wait
        await message.reply(
            f"⏳ تم حفظ كلمتك السرية (<b>{word}</b>) بنجاح.\n"
            f"بانتظار أن يكتب خصمك كلمته السرية لبدء اللعب فوراً.",
            parse_mode="HTML"
        )

# Handle Turn Actions
@router.callback_query(F.data.startswith("turn_action:"))
async def handle_turn_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match or match.state != MatchState.PLAYING:
        await callback.answer("⚠️ لا توجد مباراة نشطة جارية حالياً.", show_alert=True)
        return
        
    current_player = match.get_current_player()
    if not current_player or current_player.user_id != user_id:
        await callback.answer("⚠️ ليس دورك الآن! يرجى انتظار دور الخصم.", show_alert=True)
        return
        
    # Remove buttons from the message to prevent double-clicking
    await callback.message.edit_reply_markup(reply_markup=None)
    
    if action == "ask":
        await state.set_state(PlayerStates.asking_question)
        await callback.message.answer("❓ يرجى كتابة السؤال الموجه لخصمك وإرساله الآن:")
        await callback.answer()
        
    elif action == "guess":
        await state.set_state(PlayerStates.making_guess)
        await callback.message.answer("🎯 يرجى كتابة التخمين للشيء السري الخاص بخصمك وإرساله الآن:")
        await callback.answer()
        
    elif action == "withdraw":
        opponent = match.get_opponent(user_id)
        player = match.get_player_by_id(user_id)
        
        # End game via withdrawal
        await callback.answer("🚪 جاري الانسحاب...")
        await end_match(callback.bot, state.storage, match, winner=opponent, loser=player, reason="withdrawal")

# Process Question Input
@router.message(PlayerStates.asking_question)
async def process_question(message: types.Message, state: FSMContext):
    question_text = message.text.strip()
    user_id = message.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match or match.state != MatchState.PLAYING:
        await state.clear()
        await message.reply("⚠️ لا توجد مباراة نشطة حالياً.")
        return
        
    current_player = match.get_current_player()
    if not current_player or current_player.user_id != user_id:
        await state.clear()
        await message.reply("⚠️ ليس دورك للعب الآن.")
        return
        
    if not question_text:
        await message.reply("⚠️ يرجى إرسال سؤال نصي صالح:")
        return
        
    # Save pending question details
    match.pending_question = {
        "text": question_text,
        "asker_id": user_id
    }
    
    # Clear FSM State
    await state.clear()
    
    opponent = match.get_opponent(user_id)
    
    # Build yes/no keyboard for opponent
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ نعم", callback_data="answer_question:yes")
    builder.button(text="❌ لا", callback_data="answer_question:no")
    builder.adjust(2)
    
    # Send to opponent
    await message.bot.send_message(
        chat_id=opponent.user_id,
        text=f"❓ <b>سؤال موجه لك من خصمك ({current_player.full_name}):</b>\n"
             f"💬 <i>\"{question_text}\"</i>\n\n"
             f"يرجى الإجابة عن السؤال بصدق وأمانة:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    
    await message.reply("⏳ تم إرسال سؤالك لخصمك. بانتظار إجابته...")

# Handle Question Answer
@router.callback_query(F.data.startswith("answer_question:"))
async def handle_question_answer(callback: types.CallbackQuery, state: FSMContext):
    ans_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match or match.state != MatchState.PLAYING or not match.pending_question:
        await callback.answer("⚠️ لا يوجد سؤال معلق للإجابة عليه.", show_alert=True)
        return
        
    asker_id = match.pending_question["asker_id"]
    if user_id == asker_id:
        await callback.answer("⚠️ لا يمكنك الإجابة عن سؤالك الخاص!", show_alert=True)
        return
        
    # Remove keyboard
    await callback.message.edit_reply_markup(reply_markup=None)
    
    question_text = match.pending_question["text"]
    ans_emoji = "✅ نعم" if ans_type == "yes" else "❌ لا"
    
    asker = match.get_player_by_id(asker_id)
    answerer = match.get_player_by_id(user_id)
    
    # Add to history
    log_entry = (
        f"👤 <b>{asker.full_name}:</b>\n"
        f"💬 {question_text}\n"
        f"الجواب: {ans_emoji}\n"
        f"----------------------"
    )
    match.history.append(log_entry)
    
    # Increment question count
    asker.questions_count += 1
    
    # Clear pending question
    match.pending_question = None
    
    # Switch turn
    match.switch_turn()
    
    # Get bot info dynamically
    bot_info = await callback.bot.get_me()
    
    # Update channel message
    try:
        await callback.bot.edit_message_text(
            chat_id=match.channel_id,
            message_id=match.channel_message_id,
            text=match.format_match_message(bot_info.username),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error editing message: {e}")
        
    # Notify asker of the answer
    await callback.bot.send_message(
        chat_id=asker.user_id,
        text=f"💬 <b>إجابة خصمك على سؤالك:</b>\n"
             f"❓ السؤال: <i>\"{question_text}\"</i>\n"
             f"💬 الإجابة: {ans_emoji}\n\n"
             f"الدور الآن عند خصمك (<b>{answerer.full_name}</b>). يرجى انتظاره.",
        parse_mode="HTML"
    )
    
    await callback.answer()
    
    # Trigger turn for next player dynamically
    await start_player_turn(callback.bot, state.storage, match)

# Process Guess Input
@router.message(PlayerStates.making_guess)
async def process_guess(message: types.Message, state: FSMContext):
    guess_text = message.text.strip()
    user_id = message.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match or match.state != MatchState.PLAYING:
        await state.clear()
        await message.reply("⚠️ لا توجد مباراة نشطة حالياً.")
        return
        
    current_player = match.get_current_player()
    if not current_player or current_player.user_id != user_id:
        await state.clear()
        await message.reply("⚠️ ليس دورك للعب الآن.")
        return
        
    if not guess_text:
        await message.reply("⚠️ يرجى إرسال تخمين صالح:")
        return
        
    # Save pending guess details
    match.pending_guess = {
        "text": guess_text,
        "guesser_id": user_id
    }
    
    # Clear FSM State
    await state.clear()
    
    opponent = match.get_opponent(user_id)
    
    # Build yes/no keyboard for opponent
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ صحيح", callback_data="answer_guess:correct")
    builder.button(text="❌ خطأ", callback_data="answer_guess:incorrect")
    builder.adjust(2)
    
    # Send to opponent
    await message.bot.send_message(
        chat_id=opponent.user_id,
        text=f"🎯 <b>تخمين موجه لك من خصمك ({current_player.full_name}):</b>\n"
             f"💬 هل الشيء السري الذي اخترته هو: <b>\"{guess_text}\"</b>؟\n\n"
             f"يرجى التحقق والإجابة بصدق وأمانة:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    
    await message.reply("⏳ تم إرسال تخمينك لخصمك. بانتظار التحقق من الإجابة...")

# Handle Guess Verification
@router.callback_query(F.data.startswith("answer_guess:"))
async def handle_guess_answer(callback: types.CallbackQuery, state: FSMContext):
    ans_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    match = registry.get_match_by_user(user_id)
    if not match or match.state != MatchState.PLAYING or not match.pending_guess:
        await callback.answer("⚠️ لا يوجد تخمين معلق للتحقق منه.", show_alert=True)
        return
        
    guesser_id = match.pending_guess["guesser_id"]
    if user_id == guesser_id:
        await callback.answer("⚠️ لا يمكنك التحقق من تخمينك الخاص!", show_alert=True)
        return
        
    # Remove keyboard
    await callback.message.edit_reply_markup(reply_markup=None)
    
    guess_text = match.pending_guess["text"]
    guesser = match.get_player_by_id(guesser_id)
    opponent = match.get_player_by_id(user_id)
    
    if ans_type == "correct":
        # Increment guess count
        guesser.guesses_count += 1
        
        # Correct guess! Add to history
        log_entry = (
            f"👤 <b>{guesser.full_name}:</b>\n"
            f"🎯 تخمين: {guess_text}\n"
            f"النتيجة: ✅ صحيح\n"
            f"----------------------"
        )
        match.history.append(log_entry)
        
        # End game
        await callback.answer("🎯 تخمين صحيح! انتهت المباراة.")
        await end_match(callback.bot, state.storage, match, winner=guesser, loser=opponent, reason="guess")
        
    elif ans_type == "incorrect":
        # Increment guess count
        guesser.guesses_count += 1
        
        # Incorrect guess. Add to history
        log_entry = (
            f"👤 <b>{guesser.full_name}:</b>\n"
            f"🎯 تخمين: {guess_text}\n"
            f"النتيجة: ❌ خطأ\n"
            f"----------------------"
        )
        match.history.append(log_entry)
        
        # Clear pending guess
        match.pending_guess = None
        
        # Switch turn
        match.switch_turn()
        
        # Get bot info dynamically
        bot_info = await callback.bot.get_me()
        
        # Update channel message
        try:
            await callback.bot.edit_message_text(
                chat_id=match.channel_id,
                message_id=match.channel_message_id,
                text=match.format_match_message(bot_info.username),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error editing message: {e}")
            
        # Notify guesser
        await callback.bot.send_message(
            chat_id=guesser.user_id,
            text=f"❌ <b>إجابة خصمك: التخمين خاطئ!</b>\n"
                 f"🎯 التخمين كان: <i>\"{guess_text}\"</i>\n\n"
                 f"انتقل الدور لخصمك (<b>{opponent.full_name}</b>). يرجى انتظاره.",
            parse_mode="HTML"
        )
        
        await callback.answer()
        
        # Trigger turn for next player dynamically
        await start_player_turn(callback.bot, state.storage, match)

# End Match function (shared)
async def end_match(bot, storage, match: Match, winner: Optional[Player], loser: Optional[Player], reason: str):
    match.state = MatchState.FINISHED
    
    # 1. Delete original match message in channel
    if match.channel_message_id:
        try:
            await bot.delete_message(chat_id=match.channel_id, message_id=match.channel_message_id)
        except Exception as e:
            print(f"Error deleting match message from channel: {e}")
            
    # 2. Extract guesses list from history
    guesses_list = []
    for entry in match.history:
        if "تخمين" in entry:
            lines = entry.split("\n")
            asker_line = lines[0].replace("👤 <b>", "").replace(":</b>", "") if len(lines) > 0 else ""
            guess_line = lines[1].replace("🎯 تخمين: ", "") if len(lines) > 1 else ""
            res_line = lines[2].replace("النتيجة: ", "") if len(lines) > 2 else ""
            guesses_list.append(f"🔹 {asker_line}: تخمين ({guess_line}) -> {res_line}")
            
    guesses_str = "\n".join(guesses_list) if guesses_list else "<i>لا توجد تخمينات خاطئة.</i>"
    
    p1 = match.players[0]
    p2 = match.players[1]
    
    if reason == "guess" and winner:
        summary_title = f"🎉 <b>انتهت المباراة بفوز {winner.full_name}!</b> 🎉"
        result_text = f"🏆 <b>الفائز السريع بالأفكار:</b> <a href='tg://user?id={winner.user_id}'>{winner.full_name}</a>\n"
    elif reason == "withdrawal" and winner:
        summary_title = f"🏁 <b>انتهت المباراة بانسحاب {loser.full_name}!</b> 🏁"
        result_text = f"🏆 <b>الفائز (بالانسحاب):</b> <a href='tg://user?id={winner.user_id}'>{winner.full_name}</a>\n"
    elif reason == "draw":
        summary_title = "🏁 <b>انتهت المباراة بالتعادل!</b> 🏁"
        result_text = "🤝 <b>انتهت المباراة بالتعادل لنفاد جميع الأسئلة والتخمينات المتاحة لكلا اللاعبين.</b>\n"
    else:
        summary_title = "🏁 <b>انتهت المباراة!</b> 🏁"
        result_text = "انتهت المباراة بقرار إداري.\n"
        
    summary_text = (
        f"{summary_title}\n\n"
        f"🏷️ <b>التصنيف:</b> {match.category}\n\n"
        f"👤 <b>اللاعب الأول:</b> {p1.full_name}\n"
        f"🔑 <b>كلمته السرية:</b> <code>{p1.secret_word}</code>\n"
        f"📊 <b>الأسئلة:</b> {p1.questions_count} | <b>التخمينات:</b> {p1.guesses_count}\n\n"
        f"👤 <b>اللاعب الثاني:</b> {p2.full_name}\n"
        f"🔑 <b>كلمته السرية:</b> <code>{p2.secret_word}</code>\n"
        f"📊 <b>الأسئلة:</b> {p2.questions_count} | <b>التخمينات:</b> {p2.guesses_count}\n\n"
        f"{result_text}\n"
        f"📝 <b>سجل التخمينات:</b>\n"
        f"{guesses_str}"
    )
    
    # 3. Post summary in channel
    try:
        await bot.send_message(
            chat_id=match.channel_id,
            text=summary_text,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error posting match summary to channel: {e}")
        
    # 4. Notify players and clean FSM contexts
    for p in match.players:
        try:
            if reason == "draw":
                role_text = "🤝 <b>انتهت المباراة بالتعادل! لقد نفدت كل الأسئلة والتخمينات لكلا الطرفين.</b>"
            else:
                role_text = "🎉 <b>مبارك! لقد فزت في المباراة!</b> 🏆" if winner and p.user_id == winner.user_id else "🎮 <b>حظاً أوفر في المرة القادمة!</b>"
            
            await bot.send_message(
                chat_id=p.user_id,
                text=f"🏁 <b>انتهت المباراة!</b>\n\n"
                     f"{role_text}\n\n"
                     f"تم نشر النتائج التفصيلية والكلمات السرية في القناة.",
                parse_mode="HTML"
            )
            
            # Clear FSM State using the passed storage and base StorageKey
            state_context = FSMContext(
                storage=storage,
                key=StorageKey(
                    bot_id=bot.id,
                    chat_id=p.user_id,
                    user_id=p.user_id
                )
            )
            await state_context.clear()
        except Exception as e:
            print(f"Error cleaning FSM/notifying player {p.user_id}: {e}")
            
    # 5. Clean up from registry
    registry.remove_match(match.match_id)
