"""
Inline клавиатуры
"""
from datetime import datetime
from typing import List, Dict
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from backend import config


def format_slot_button_text(slot: Dict) -> str:
    """
    Форматирует текст для кнопки со слотом
    
    Args:
        slot: Словарь с информацией о слоте
        
    Returns:
        Текст для кнопки, например: "Сегодня 10:00-11:00"
    """
    day = slot['day']
    time = slot['time']
    
    # Сокращаем длинные названия дней для кнопок
    if day.startswith('Понедельник'):
        day = 'Пн'
    elif day.startswith('Вторник'):
        day = 'Вт'
    elif day.startswith('Среда'):
        day = 'Ср'
    elif day.startswith('Четверг'):
        day = 'Чт'
    elif day.startswith('Пятница'):
        day = 'Пт'
    elif day.startswith('Суббота'):
        day = 'Сб'
    elif day.startswith('Воскресенье'):
        day = 'Вс'
    elif day == 'Сегодня':
        day = 'Сегодня'
    elif day == 'Завтра':
        day = 'Завтра'
    elif ',' in day:
        # Если формат "Понедельник, 15 января", берем только день недели
        day = day.split(',')[0]
        # Сокращаем
        day_abbr = {
            'Понедельник': 'Пн',
            'Вторник': 'Вт',
            'Среда': 'Ср',
            'Четверг': 'Чт',
            'Пятница': 'Пт',
            'Суббота': 'Сб',
            'Воскресенье': 'Вс'
        }
        day = day_abbr.get(day, day)
    
    return f"{day} {time}"


def create_slots_keyboard(slots: List[Dict], max_slots: int = 30, columns: int = 2) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками свободных слотов
    
    Args:
        slots: Список свободных слотов
        max_slots: Максимальное количество слотов для отображения
        columns: Количество кнопок в ряду
        
    Returns:
        InlineKeyboardMarkup с кнопками
    """
    keyboard = []
    
    # Ограничиваем количество слотов
    display_slots = slots[:max_slots]
    
    # Создаем кнопки
    row = []
    for slot in display_slots:
        button_text = format_slot_button_text(slot)
        # Callback data содержит datetime_start для идентификации
        callback_data = f"slot_{slot['datetime_start']}"
        
        row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
        
        # Добавляем ряд, когда набралось нужное количество кнопок
        if len(row) == columns:
            keyboard.append(row)
            row = []
    
    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)
    
    # Кнопки управления
    control_row = []
    if len(display_slots) < len(slots):
        control_row.append(InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_slots"))
    control_row.append(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking"))
    
    if control_row:
        keyboard.append(control_row)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_events_keyboard(events: List[Dict], action: str = "reschedule") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками записей пользователя
    
    Args:
        events: Список событий пользователя
        action: Действие - "reschedule" или "cancel"
        
    Returns:
        InlineKeyboardMarkup с кнопками
    """
    keyboard = []
    
    for i, event in enumerate(events, 1):
        button_text = f"{i}. {event['day']} {event['time']}"
        
        if action == "reschedule":
            callback_data = f"reschedule_{event['id']}"
        elif action == "cancel":
            callback_data = f"cancel_event_{event['id']}"
        else:
            callback_data = f"event_{event['id']}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            )
        ])
    
    cancel_text = "cancel_reschedule" if action == "reschedule" else "cancel_cancel"
    keyboard.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_text)
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создает главное меню с основными действиями (inline)
    
    Returns:
        InlineKeyboardMarkup с кнопками главного меню
    """
    keyboard = [
        [
            InlineKeyboardButton(text="📅 Записаться", callback_data="menu_book"),
            InlineKeyboardButton(text="📋 Мои записи", callback_data="menu_my_booking")
        ],
        [
            InlineKeyboardButton(text="🔄 Перенести", callback_data="menu_reschedule"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="menu_cancel")
        ],
        [
            InlineKeyboardButton(text="💬 Частые вопросы", callback_data="show_faq_menu"),
            InlineKeyboardButton(text="🔗 Наши сообщества", callback_data="show_communities_menu")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Справка", callback_data="menu_help")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def add_back_to_menu_button(keyboard: list) -> list:
    """
    Добавляет кнопку "Назад в меню" к существующей клавиатуре
    
    Args:
        keyboard: Список рядов кнопок
        
    Returns:
        Обновленная клавиатура с кнопкой "Назад"
    """
    keyboard.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")
    ])
    return keyboard


def get_faq_menu() -> InlineKeyboardMarkup:
    """
    Создает меню для раздела FAQ с кнопками для разных тем
    
    Returns:
        InlineKeyboardMarkup с кнопками FAQ
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="🚀 Как проходит пробный урок?",
                callback_data="faq_trial_lesson"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎓 Какие есть курсы?",
                callback_data="faq_courses"
            )
        ],
        [
            InlineKeyboardButton(
                text="💳 Как происходит оплата?",
                callback_data="faq_payment"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад в главное меню",
                callback_data="back_to_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_communities_menu() -> InlineKeyboardMarkup:
    """
    Создает меню с кнопками для сообществ
    
    Returns:
        InlineKeyboardMarkup с кнопками сообществ
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📢 Наш Telegram",
                url="https://t.me/no_bugs_python"
            )
        ],
        [
            InlineKeyboardButton(
                text="💡 Наш ВКонтакте",
                url="https://vk.com/nobugs_python"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад в главное меню",
                callback_data="back_to_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


