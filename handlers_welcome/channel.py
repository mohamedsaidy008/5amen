import os
import json
from aiogram import Router, types
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import ChatMemberUpdated

router = Router()

SETTINGS_FILE = "welcome_settings.json"

def load_welcome_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {
            "welcome_enabled": True,
            "ban_on_leave_enabled": True,
            "welcome_text": "مرحباً بك يا {name} نورتنا القناة قناتك لا عاد تطلع 🌹",
            "banned_users": {}
        }
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            "welcome_enabled": True,
            "ban_on_leave_enabled": True,
            "welcome_text": "مرحباً بك يا {name} نورتنا القناة قناتك لا عاد تطلع 🌹",
            "banned_users": {}
        }

def save_welcome_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving welcome settings: {e}")

@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def handle_member_joined(event: ChatMemberUpdated):
    settings = load_welcome_settings()
    if not settings.get("welcome_enabled", True):
        return
        
    user = event.new_chat_member.user
    name = user.full_name
    
    welcome_template = settings.get("welcome_text", "مرحباً بك يا {name} نورتنا القناة قناتك لا عاد تطلع 🌹")
    welcome_msg = welcome_template.replace("{name}", name).replace("{username}", f"@{user.username}" if user.username else name)
    
    try:
        await event.bot.send_message(
            chat_id=event.chat.id,
            text=welcome_msg,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error sending welcome message in chat {event.chat.id}: {e}")

@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def handle_member_left(event: ChatMemberUpdated):
    settings = load_welcome_settings()
    if not settings.get("ban_on_leave_enabled", True):
        return
        
    user = event.old_chat_member.user
    user_id = user.id
    name = user.full_name
    chat_id = event.chat.id
    
    # Do not ban if they left because they are administrators
    if event.old_chat_member.status in ["administrator", "creator"]:
        return
        
    try:
        # Ban the user from the channel
        await event.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        
        # Save to banned users
        settings = load_welcome_settings()
        settings["banned_users"][str(user_id)] = {
            "name": name,
            "chat_id": chat_id,
            "chat_title": event.chat.title
        }
        save_welcome_settings(settings)
        
        print(f"User {name} ({user_id}) left chat {chat_id} and was banned automatically.")
    except Exception as e:
        print(f"Error banning user {user_id} on leave in chat {chat_id}: {e}")
