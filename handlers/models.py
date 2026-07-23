import uuid
import json
import os
from enum import Enum
from typing import Dict, List, Optional

class MatchState(Enum):
    CREATED = 1
    JOINING = 2
    CHOOSING_WORDS = 3
    APPROVING_WORDS = 4
    PLAYING = 5
    FINISHED = 6

class Player:
    def __init__(self, user_id: int, full_name: str, username: Optional[str] = None):
        self.user_id = user_id
        self.full_name = full_name
        self.username = username
        self.secret_word: Optional[str] = None
        self.word_approved: bool = False
        self.questions_count: int = 0
        self.guesses_count: int = 0

class Match:
    def __init__(self, match_id: str, channel_id: int, channel_title: str, category: str, creator_id: int):
        self.match_id = match_id
        self.channel_id = channel_id
        self.channel_title = channel_title
        self.category = category
        self.creator_id = creator_id
        self.state: MatchState = MatchState.CREATED
        
        self.players: List[Player] = []
        self.turn_index: int = 0  # 0 or 1 (indicates index in self.players)
        
        self.channel_message_id: Optional[str] = None
        self.history: List[str] = []
        
        # Turn limits (None means unlimited)
        self.max_questions: Optional[int] = None
        self.max_guesses: Optional[int] = None
        
        # Flag if match is played in a group or via inline query instead of a channel
        self.is_group_match: bool = False
        
        # Pending turn actions
        self.pending_question: Optional[dict] = None  # {"text": str}
        self.pending_guess: Optional[dict] = None     # {"text": str}

    def get_current_player(self) -> Optional[Player]:
        if len(self.players) < 2:
            return None
        return self.players[self.turn_index]

    def get_opponent(self, player_id: int) -> Optional[Player]:
        if len(self.players) < 2:
            return None
        if self.players[0].user_id == player_id:
            return self.players[1]
        elif self.players[1].user_id == player_id:
            return self.players[0]
        return None

    def get_player_by_id(self, player_id: int) -> Optional[Player]:
        for p in self.players:
            if p.user_id == player_id:
                return p
        return None

    def switch_turn(self):
        self.turn_index = 1 - self.turn_index

    def format_match_message(self, bot_username: Optional[str] = None) -> str:
        p1 = self.players[0] if len(self.players) > 0 else None
        p2 = self.players[1] if len(self.players) > 1 else None
        
        p1_name = f"<a href='tg://user?id={p1.user_id}'>{p1.full_name}</a>" if p1 else "بانتظار الانضمام..."
        p2_name = f"<a href='tg://user?id={p2.user_id}'>{p2.full_name}</a>" if p2 else "بانتظار الانضمام..."
        
        p1_q = f"{p1.questions_count}/{self.max_questions}" if self.max_questions is not None and p1 else (p1.questions_count if p1 else 0)
        p2_q = f"{p2.questions_count}/{self.max_questions}" if self.max_questions is not None and p2 else (p2.questions_count if p2 else 0)
        
        p1_g = f"{p1.guesses_count}/{self.max_guesses}" if self.max_guesses is not None and p1 else (p1.guesses_count if p1 else 0)
        p2_g = f"{p2.guesses_count}/{self.max_guesses}" if self.max_guesses is not None and p2 else (p2.guesses_count if p2 else 0)
        
        current_player = self.get_current_player()
        current_turn_name = current_player.full_name if current_player else "—"
        
        place_label = "المجموعة" if self.is_group_match else "القناة"
        
        text = f"🎮 <b>مباراة تخمين جديدة!</b>\n"
        if not self.is_group_match and self.channel_id != 0:
            text += f"📢 <b>{place_label}:</b> {self.channel_title}\n"
        text += f"🏷️ <b>التصنيف:</b> {self.category}\n\n"
        
        text += (
            f"👤 <b>اللاعب الأول:</b> {p1_name}\n"
            f"👤 <b>اللاعب الثاني:</b> {p2_name}\n\n"
        )
        
        if self.state == MatchState.PLAYING:
            text += (
                f"📊 <b>إحصائيات الجولة:</b>\n"
                f"🔹 {p1.full_name}: {p1_q} سؤال | {p1_g} تخمين\n"
                f"🔹 {p2.full_name}: {p2_q} سؤال | {p2_g} تخمين\n\n"
                f"🔔 <b>الدور الحالي عند:</b> {current_turn_name}\n\n"
                f"📝 <b>سجل المباراة:</b>\n"
            )
            if self.history:
                # Show last 10 log entries
                for entry in self.history[-10:]:
                    text += f"{entry}\n"
            else:
                text += "<i>بدأت المباراة، بانتظار السؤال الأول...</i>\n"
        elif self.state == MatchState.CHOOSING_WORDS or self.state == MatchState.APPROVING_WORDS:
            text += "⏳ <b>بانتظار اختيار الكلمات السرية من قبل اللاعبين...</b>\n"
        elif self.state == MatchState.JOINING:
            text += f"⏳ <b>بانتظار انضمام اللاعبين ({len(self.players)}/2)...</b>\n"
            if bot_username:
                text += f"🤖 <i>قبل الضغط على زر الانضمام، يرجى بدء البوت في الخاص بالضغط هنا: @{bot_username}</i>\n"
            
        return text

class MatchRegistry:
    def __init__(self):
        self.active_matches: Dict[str, Match] = {}       # match_id -> Match
        self.channel_matches: Dict[int, Match] = {}      # channel_id -> Match (excluding 0)
        self.inline_matches: Dict[str, Match] = {}       # inline_message_id -> Match
        self.user_matches: Dict[int, Match] = {}         # user_id -> Match (currently playing)
        self.admin_creation: Dict[int, dict] = {}        # admin_id -> temp match creation state
        
        # Channels persistence file
        self.saved_channels_file = "saved_channels.json"

    def load_saved_channels(self) -> Dict[str, str]:
        if not os.path.exists(self.saved_channels_file):
            return {}
        try:
            with open(self.saved_channels_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading saved channels: {e}")
            return {}

    def save_channel(self, channel_id: int, channel_title: str):
        if channel_id == 0:
            return
        channels = self.load_saved_channels()
        channels[str(channel_id)] = channel_title
        try:
            with open(self.saved_channels_file, 'w', encoding='utf-8') as f:
                json.dump(channels, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving channel: {e}")

    def create_match(self, channel_id: int, channel_title: str, category: str, creator_id: int) -> Match:
        match_id = uuid.uuid4().hex[:8]
        
        if channel_id != 0 and channel_id in self.channel_matches:
            old_match = self.channel_matches[channel_id]
            self.remove_match(old_match.match_id)
            
        match = Match(match_id, channel_id, channel_title, category, creator_id)
        match.state = MatchState.JOINING
        
        self.active_matches[match_id] = match
        if channel_id != 0:
            self.channel_matches[channel_id] = match
        return match

    def create_inline_match(self, inline_message_id: str, category: str, creator_id: int) -> Match:
        match_id = uuid.uuid4().hex[:8]
        match = Match(match_id, 0, "مباراة سريعة", category, creator_id)
        match.is_group_match = True
        match.channel_message_id = inline_message_id
        match.state = MatchState.JOINING
        
        self.active_matches[match_id] = match
        self.inline_matches[inline_message_id] = match
        return match

    def get_match_by_id(self, match_id: str) -> Optional[Match]:
        return self.active_matches.get(match_id)

    def get_match_by_inline_id(self, inline_message_id: str) -> Optional[Match]:
        return self.inline_matches.get(inline_message_id)

    def get_match_by_channel(self, channel_id: int) -> Optional[Match]:
        if channel_id == 0:
            return None
        return self.channel_matches.get(channel_id)

    def get_match_by_user(self, user_id: int) -> Optional[Match]:
        return self.user_matches.get(user_id)

    def add_player_to_match(self, match_id: str, user_id: int, full_name: str, username: Optional[str]) -> bool:
        match = self.get_match_by_id(match_id)
        if not match or len(match.players) >= 2 or match.state != MatchState.JOINING:
            return False
            
        player = Player(user_id, full_name, username)
        match.players.append(player)
        self.user_matches[user_id] = match
        return True

    def remove_match(self, match_id: str):
        match = self.active_matches.get(match_id)
        if not match:
            return
            
        # Remove from user_matches
        for p in match.players:
            if p.user_id in self.user_matches:
                del self.user_matches[p.user_id]
                
        # Remove from channel_matches
        if match.channel_id != 0 and match.channel_id in self.channel_matches:
            del self.channel_matches[match.channel_id]
            
        # Remove from inline_matches
        if match.channel_message_id and match.channel_message_id in self.inline_matches:
            del self.inline_matches[match.channel_message_id]
            
        # Remove from active_matches
        if match_id in self.active_matches:
            del self.active_matches[match_id]

# Singleton registry
registry = MatchRegistry()
