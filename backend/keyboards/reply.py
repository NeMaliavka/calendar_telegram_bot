"""
Reply клавиатуры (боковое меню)
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает боковое меню (ReplyKeyboardMarkup)
    
    Returns:
        ReplyKeyboardMarkup с основными кнопками
    """
    keyboard = [
        [
            KeyboardButton(text="📅 Записаться"),
            KeyboardButton(text="📋 Мои записи")
        ],
        [
            KeyboardButton(text="🔄 Перенести"),
            KeyboardButton(text="❌ Отменить")
        ],
        [
            KeyboardButton(text="ℹ️ Справка")
        ]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие из меню"
    )


