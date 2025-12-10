"""
Обработчики команд бота
"""
import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from backend.keyboards.reply import get_main_reply_keyboard
from backend.keyboards.inline import create_main_menu_keyboard
from backend.services.calendar_service import CalendarService
from backend.services.booking_service import BookingService
from backend.keyboards.inline import create_slots_keyboard, add_back_to_menu_button
from backend.keyboards.inline import create_events_keyboard
from aiogram.enums import ChatAction

# Импорты для работы с БД
from backend.db.database import get_or_create_parent, get_full_parent_data
from typing import Optional
from backend.utils.typing_indicator import TypingContext

logger = logging.getLogger(__name__)

router = Router()

# Глобальные переменные для сервисов (устанавливаются в setup_commands_handlers)
_calendar_service: Optional[CalendarService] = None
_booking_service: Optional[BookingService] = None


async def cmd_book(message: Message, state: FSMContext, 
                   calendar_service: Optional[CalendarService] = None,
                   booking_service: Optional[BookingService] = None):
    """
    Функция для начала бронирования.
    Может быть вызвана как обработчик команды или напрямую из других модулей.
    """
    # Используем переданные сервисы или глобальные
    cal_service = calendar_service or _calendar_service
    book_service = booking_service or _booking_service
    
    if not cal_service or not book_service:
        await message.answer(
            "❌ Сервис календаря недоступен. "
            "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
            reply_markup=get_main_reply_keyboard()
        )
        return
    
    try:
        await message.answer("🔍 Ищу свободное время...")
        
        # Показываем индикатор во время поиска слотов
        async with TypingContext(message.bot, message.from_user.id):
            # Получаем слоты на ближайшие дни (начиная со следующего дня)
            slots = cal_service.get_free_slots(days=7, skip_today=True)
        
        if not slots:
            await message.answer(
                "😔 К сожалению, на ближайшие дни нет свободного времени.\n"
                "Попробуйте позже или свяжитесь с администратором.",
                reply_markup=get_main_reply_keyboard()
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
        
        await message.answer(
            message_text,
            reply_markup=keyboard
        )
        
        # Переходим в состояние выбора слота
        from backend.states import BookingStates
        await state.set_state(BookingStates.selecting_slot)
        
    except Exception as e:
        logger.error(f"Ошибка в cmd_book: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_reply_keyboard()
        )


async def cmd_cancel(message: Message, state: FSMContext,
                     calendar_service: Optional[CalendarService] = None):
    """
    Функция для отмены записи.
    Может быть вызвана как обработчик команды или напрямую из других модулей.
    """
    # Используем переданный сервис или глобальный
    cal_service = calendar_service or _calendar_service
    
    if not cal_service:
        await message.answer(
            "❌ Сервис календаря недоступен. "
            "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
            reply_markup=get_main_reply_keyboard()
        )
        return
    
    try:
        await message.answer("🔍 Ищу ваши записи...")
        
        user = message.from_user
        user_id = user.id
        user_username = user.username
        
        # Показываем индикатор во время поиска записей
        async with TypingContext(message.bot, user_id):
            # Получаем события пользователя
            events = cal_service.get_user_events(
                user_id=user_id,
                user_username=user_username,
                days_ahead=30
            )
        
        if not events:
            await message.answer(
                "📭 У вас нет активных записей для отмены.\n\n"
                "Используйте кнопку 'Записаться' для записи.",
                reply_markup=get_main_reply_keyboard()
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
        
        await message.answer(
            message_text,
            reply_markup=keyboard
        )
        
        # Сохраняем события в состоянии
        await state.update_data(events=events)
        from backend.states import BookingStates
        await state.set_state(BookingStates.selecting_event_to_cancel)
        
    except Exception as e:
        logger.error(f"Ошибка в cmd_cancel: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_reply_keyboard()
        )


def setup_commands_handlers(
    dp,
    calendar_service: CalendarService,
    booking_service: BookingService
):
    """
    Настраивает обработчики команд
    
    Args:
        dp: Dispatcher
        calendar_service: Сервис календаря
        booking_service: Сервис бронирования
    """
    # Сохраняем сервисы для использования в обработчиках
    global _calendar_service, _booking_service
    _calendar_service = calendar_service
    _booking_service = booking_service
    router.calendar_service = calendar_service
    router.booking_service = booking_service
    
    @router.message(CommandStart())
    async def cmd_start(message: Message):
        """Обработчик команды /start"""
        user = message.from_user
        
        # Создаем или получаем пользователя в БД
        try:
            parent = await get_or_create_parent(
                telegram_id=user.id,
                username=user.username
            )
            if parent:
                logger.info(f"Пользователь {user.id} найден/создан в БД (Parent ID: {parent.id})")
            else:
                logger.warning(f"БД недоступна. Пользователь {user.id} работает без сохранения в БД.")
        except Exception as e:
            logger.error(f"Ошибка при работе с БД в /start: {e}", exc_info=True)
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я бот для записи на пробное занятие.\n\n"
            "Выберите действие из меню ниже 👇"
        )
        # Боковое меню (ReplyKeyboardMarkup)
        reply_keyboard = get_main_reply_keyboard()
        await message.answer(welcome_text, reply_markup=reply_keyboard)
    
    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """Обработчик команды /help"""
        help_text = (
            "📋 Доступные действия:\n\n"
            "📅 Записаться - выбрать время и записаться на пробное занятие\n"
            "📋 Мои записи - посмотреть все ваши активные записи\n"
            "🔄 Перенести - перенести существующую запись на другое время\n"
            "❌ Отменить - отменить запись\n\n"
            "💡 Все действия доступны через боковое меню или команды:\n"
            "/book - записаться\n"
            "/my_booking - мои записи\n"
            "/reschedule - перенести\n"
            "/cancel - отменить\n\n"
            "Используйте /start для открытия главного меню."
        )
        reply_keyboard = get_main_reply_keyboard()
        await message.answer(help_text, reply_markup=reply_keyboard)
    
    @router.message(Command("faq"))
    async def cmd_faq(message: Message):
        """Обработчик команды /faq - показывает меню с частыми вопросами"""
        from backend.keyboards.inline import get_faq_menu
        await message.answer(
            "Выберите интересующий вас вопрос из списка:",
            reply_markup=get_faq_menu()
        )
    
    @router.message(Command("community_tg"))
    async def cmd_community_tg(message: Message):
        """Обработчик команды /community_tg - ссылка на Telegram канал"""
        await message.answer(
            "📢 Присоединяйтесь к нашему Telegram-каналу: https://t.me/no_bugs_python"
        )
    
    @router.message(Command("community_vk"))
    async def cmd_community_vk(message: Message):
        """Обработчик команды /community_vk - ссылка на ВКонтакте"""
        await message.answer(
            "💡 Мы также есть во ВКонтакте! Присоединяйтесь: https://vk.com/nobugs_python"
        )
    
    @router.message(Command("book", "booking"))
    @router.message(F.text == "📅 Записаться")
    async def cmd_book_handler(message: Message, state: FSMContext):
        """Обработчик команды /book - начало бронирования"""
        await cmd_book(message, state, calendar_service, booking_service)
    
    @router.message(Command("my_booking", "my_lessons"))
    @router.message(F.text == "📋 Мои записи")
    async def cmd_my_booking(message: Message):
        """Обработчик команды /my_booking - проверка своих записей"""
        try:
            await message.answer("🔍 Ищу ваши записи...")
            
            user = message.from_user
            user_id = user.id
            
            # Показываем индикатор во время поиска записей в БД
            async with TypingContext(message.bot, user_id):
                # Получаем данные из БД
                parent_data = await get_full_parent_data(user_id, user.username)
            lessons = parent_data.get('trial_lessons', [])
            
            # Фильтруем только запланированные уроки
            from backend.db.models import TrialLessonStatus
            active_lessons = [
                lesson for lesson in lessons 
                if lesson.get('status') == TrialLessonStatus.PLANNED.name
            ]
            
            if not active_lessons:
                await message.answer(
                    "📭 У вас нет активных записей на пробное занятие.\n\n"
                    "Используйте кнопку 'Записаться' для записи.",
                    reply_markup=get_main_reply_keyboard()
                )
                return
            
            # Форматируем список записей
            from backend.utils.formatters import format_date_russian, parse_datetime_iso
            from zoneinfo import ZoneInfo
            
            message_text = f"📅 Ваши записи ({len(active_lessons)}):\n\n"
            
            for i, lesson in enumerate(active_lessons, 1):
                scheduled_at = lesson.get('scheduled_at')
                if scheduled_at:
                    try:
                        dt = parse_datetime_iso(scheduled_at)
                        if dt:
                            dt_moscow = dt.astimezone(ZoneInfo("Europe/Moscow"))
                            date_str = format_date_russian(dt_moscow, 'full')
                            message_text += f"{i}. {date_str}\n"
                    except Exception as e:
                        logger.error(f"Ошибка форматирования даты: {e}")
                        message_text += f"{i}. Дата: {scheduled_at}\n"
                else:
                    message_text += f"{i}. Дата не указана\n"
                
                message_text += "\n"
            
            message_text += "💡 Используйте кнопки 'Перенести' или 'Отменить' для управления записями."
            
            await message.answer(
                message_text,
                reply_markup=get_main_reply_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Ошибка в /my_booking: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла ошибка при получении данных. Попробуйте позже.",
                reply_markup=get_main_reply_keyboard()
            )
    
    @router.message(Command("reschedule"))
    @router.message(F.text == "🔄 Перенести")
    async def cmd_reschedule(message: Message, state: FSMContext):
        """Обработчик команды /reschedule - перенос записи"""
        if not calendar_service or not booking_service:
            await message.answer(
                "❌ Сервис календаря недоступен. "
                "Проверьте настройки GOOGLE_CALENDAR_ACTIVATE в .env файле.",
                reply_markup=get_main_reply_keyboard()
            )
            return
        
        try:
            await message.answer("🔍 Ищу ваши записи...")
            
            user = message.from_user
            user_id = user.id
            user_username = user.username
            
            # Показываем индикатор во время поиска записей
            async with TypingContext(message.bot, user_id):
                # Получаем события пользователя
                events = calendar_service.get_user_events(
                    user_id=user_id,
                    user_username=user_username,
                    days_ahead=30
                )
            
            if not events:
                await message.answer(
                    "📭 У вас нет активных записей для переноса.\n\n"
                    "Используйте кнопку 'Записаться' для записи.",
                    reply_markup=get_main_reply_keyboard()
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
            
            await message.answer(
                message_text,
                reply_markup=keyboard
            )
            
            # Сохраняем события в состоянии
            await state.update_data(events=events)
            from backend.states import BookingStates
            await state.set_state(BookingStates.selecting_event_to_reschedule)
            
        except Exception as e:
            logger.error(f"Ошибка в /reschedule: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=get_main_reply_keyboard()
            )
    
    @router.message(Command("cancel"))
    @router.message(F.text == "❌ Отменить")
    async def cmd_cancel_handler(message: Message, state: FSMContext):
        """Обработчик команды /cancel - отмена записи"""
        await cmd_cancel(message, state, calendar_service)
    
    @router.message(F.text == "ℹ️ Справка")
    async def cmd_help_text(message: Message):
        """Обработка текстовой кнопки "Справка" """
        await cmd_help(message)
    
    # Регистрируем роутер
    dp.include_router(router)


