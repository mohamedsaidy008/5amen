from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_category = State()

class PlayerStates(StatesGroup):
    choosing_word = State()
    asking_question = State()
    making_guess = State()
