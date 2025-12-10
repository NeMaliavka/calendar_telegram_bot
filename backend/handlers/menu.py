"""
Обработчики inline меню
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from backend.services.calendar_service import CalendarService
from backend.services.booking_service import BookingService
from backend.keyboards.inline import (
    create_slots_keyboard,
    create_events_keyboard,
    create_main_menu_keyboard,
    add_back_to_menu_button
)
from backend.keyboards.reply import get_main_reply_keyboard
from backend.states import BookingStates

logger = logging.getLogger(__name__)

router = Router()


def setup_menu_handlers(
    dp,
    calendar_service: CalendarService,
    booking_service: BookingService
):
    """
    Настраивает обработчики меню
    
    Args:
        dp: Dispatcher
        calendar_service: Сервис календаря
        booking_service: Сервис бронирования
    """
    
    @router.callback_query(F.data == "menu_book")
    async def menu_book(callback: CallbackQuery, state: FSMContext):
        """Обработка кнопки "Записаться" из меню"""
        await callback.answer()
        
        if not calendar_service or not booking_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен. "
                "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        try:
            await callback.message.edit_text("🔍 Ищу свободное время...")
            
            # Показываем индикатор во время поиска слотов
            async with TypingContext(callback.bot, callback.from_user.id):
                # Получаем слоты на ближайшие дни (начиная со следующего дня)
                slots = calendar_service.get_free_slots(days=7, skip_today=True)
            
            if not slots:
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(
                    "😔 К сожалению, на ближайшие дни нет свободного времени.\n"
                    "Попробуйте позже или свяжитесь с администратором.",
                    reply_markup=keyboard
                )
                return
            
            # Создаем клавиатуру с кнопками
            keyboard = create_slots_keyboard(slots, max_slots=30)
            # Добавляем кнопку "Назад в меню"
            keyboard.inline_keyboard = add_back_to_menu_button(keyboard.inline_keyboard)
            
            message_text = (
                f"📅 Выберите удобное время для пробного занятия:\n\n"
                f"Найдено {len(slots)} свободных слотов.\n"
                f"Нажмите на кнопку с нужным временем 👇"
            )
            
            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )
            
            # Переходим в состояние выбора слота
            await state.set_state(BookingStates.selecting_slot)
            
        except Exception as e:
            logger.error(f"Ошибка в menu_book: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=keyboard
            )
    
    @router.callback_query(F.data == "menu_my_booking")
    async def menu_my_booking(callback: CallbackQuery):
        """Обработка кнопки "Мои записи" из меню"""
        await callback.answer()
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен. "
                "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        try:
            await callback.message.edit_text("🔍 Ищу ваши записи...")
            
            user = callback.from_user
            user_id = user.id
            user_username = user.username
            
            # Показываем индикатор во время поиска записей
            async with TypingContext(callback.bot, user_id):
                # Получаем события пользователя
                events = calendar_service.get_user_events(
                    user_id=user_id,
                    user_username=user_username,
                    days_ahead=30
                )
            
            keyboard = create_main_menu_keyboard()
            
            if not events:
                await callback.message.edit_text(
                    "📭 У вас нет активных записей на пробное занятие.\n\n"
                    "Используйте кнопку 'Записаться' для записи.",
                    reply_markup=keyboard
                )
                return
            
            # Форматируем список записей
            message_text = f"📅 Ваши записи ({len(events)}):\n\n"
            
            for i, event in enumerate(events, 1):
                message_text += (
                    f"{i}. {event['day']}\n"
                    f"   ⏰ {event['time']}\n"
                )
                
                # Парсим имя из description, если есть
                description = event.get('description', '')
                if 'Имя:' in description:
                    for line in description.split('\n'):
                        if line.startswith('Имя:'):
                            name = line.replace('Имя:', '').strip()
                            if name:
                                message_text += f"   👤 {name}\n"
                
                message_text += "\n"
            
            message_text += "💡 Используйте кнопки 'Перенести' или 'Отменить' для управления записями."
            
            await callback.message.edit_text(message_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка в menu_my_booking: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка при получении данных из календаря. Попробуйте позже.",
                reply_markup=keyboard
            )
    
    @router.callback_query(F.data == "menu_reschedule")
    async def menu_reschedule_handler(callback: CallbackQuery, state: FSMContext):
        """Обработка кнопки "Перенести" из меню"""
        await callback.answer()
        
        if not calendar_service or not booking_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен. "
                "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        try:
            await callback.message.edit_text("🔍 Ищу ваши записи...")
            
            user = callback.from_user
            user_id = user.id
            user_username = user.username
            
            # Показываем индикатор во время поиска записей
            async with TypingContext(callback.bot, user_id):
                # Получаем события пользователя
                events = calendar_service.get_user_events(
                    user_id=user_id,
                    user_username=user_username,
                    days_ahead=30
                )
            
            if not events:
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(
                    "📭 У вас нет активных записей для переноса.\n\n"
                    "Используйте кнопку 'Записаться' для записи.",
                    reply_markup=keyboard
                )
                return
            
            # Создаем клавиатуру с записями
            keyboard = create_events_keyboard(events, action="reschedule")
            # Добавляем кнопку "Назад в меню"
            keyboard.inline_keyboard = add_back_to_menu_button(keyboard.inline_keyboard)
            
            message_text = (
                f"📅 Выберите запись для переноса:\n\n"
                f"Найдено {len(events)} активных записей."
            )
            
            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )
            
            # Сохраняем события в состоянии
            await state.update_data(events=events)
            await state.set_state(BookingStates.selecting_event_to_reschedule)
            
        except Exception as e:
            logger.error(f"Ошибка в menu_reschedule: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=keyboard
            )
    
    @router.callback_query(F.data == "menu_cancel")
    async def menu_cancel_handler(callback: CallbackQuery, state: FSMContext):
        """Обработка кнопки "Отменить" из меню"""
        await callback.answer()
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен. "
                "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        try:
            await callback.message.edit_text("🔍 Ищу ваши записи...")
            
            user = callback.from_user
            user_id = user.id
            user_username = user.username
            
            # Показываем индикатор во время поиска записей
            async with TypingContext(callback.bot, user_id):
                # Получаем события пользователя
                events = calendar_service.get_user_events(
                    user_id=user_id,
                    user_username=user_username,
                    days_ahead=30
                )
            
            if not events:
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(
                    "📭 У вас нет активных записей для отмены.\n\n"
                    "Используйте кнопку 'Записаться' для записи.",
                    reply_markup=keyboard
                )
                return
            
            # Создаем клавиатуру с записями
            keyboard = create_events_keyboard(events, action="cancel")
            # Добавляем кнопку "Назад в меню"
            keyboard.inline_keyboard = add_back_to_menu_button(keyboard.inline_keyboard)
            
            message_text = (
                f"📅 Выберите запись для отмены:\n\n"
                f"Найдено {len(events)} активных записей."
            )
            
            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )
            
            # Сохраняем события в состоянии
            await state.update_data(events=events)
            await state.set_state(BookingStates.selecting_event_to_cancel)
            
        except Exception as e:
            logger.error(f"Ошибка в menu_cancel: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=keyboard
            )
    
    @router.callback_query(F.data == "menu_help")
    async def menu_help(callback: CallbackQuery):
        """Обработка кнопки "Справка" из меню"""
        await callback.answer()
        
        help_text = (
            "📋 Доступные действия:\n\n"
            "📅 Записаться - выбрать время и записаться на пробное занятие\n"
            "📋 Мои записи - посмотреть все ваши активные записи\n"
            "🔄 Перенести - перенести существующую запись на другое время\n"
            "❌ Отменить - отменить запись\n\n"
            "💡 Все действия доступны через меню или команды:\n"
            "/book - записаться\n"
            "/my_booking - мои записи\n"
            "/reschedule - перенести\n"
            "/cancel - отменить"
        )
        keyboard = create_main_menu_keyboard()
        await callback.message.edit_text(help_text, reply_markup=keyboard)
    
    # Регистрируем роутер
    dp.include_router(router)

