from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_category = State()
    waiting_for_questions_limit = State()
    waiting_for_guesses_limit = State()

class PlayerStates(StatesGroup):
    choosing_word = State()
    asking_question = State()
    making_guess = State()

class WelcomeStates(StatesGroup):
    waiting_for_welcome_text = State()
