"""
Обработчики callback запросов (inline кнопки)
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from aiogram import Bot
from backend.services.calendar_service import CalendarService
from backend.services.booking_service import BookingService
from backend.keyboards.inline import (
    create_slots_keyboard,
    create_main_menu_keyboard,
    add_back_to_menu_button,
    get_faq_menu,
    get_communities_menu
)
from backend.keyboards.reply import get_main_reply_keyboard
from backend.states import BookingStates
from backend.utils import parse_datetime_from_string
from backend.utils.typing_indicator import TypingContext
from backend import config

logger = logging.getLogger(__name__)

router = Router()


def setup_callbacks_handlers(
    dp,
    calendar_service: CalendarService,
    booking_service: BookingService
):
    """
    Настраивает обработчики callback
    
    Args:
        dp: Dispatcher
        calendar_service: Сервис календаря
        booking_service: Сервис бронирования
    """
    
    @router.callback_query(F.data == "back_to_menu")
    async def back_to_menu(callback: CallbackQuery, state: FSMContext):
        """Возврат в главное меню"""
        await callback.answer()
        await state.clear()
        
        user = callback.from_user
        welcome_text = (
            f"👋 Главное меню\n\n"
            "Выберите действие из меню ниже 👇"
        )
        inline_keyboard = create_main_menu_keyboard()
        reply_keyboard = get_main_reply_keyboard()
        await callback.message.edit_text(welcome_text, reply_markup=inline_keyboard)
        await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
    
    @router.callback_query(F.data.startswith("slot_"), BookingStates.selecting_slot)
    async def process_slot_selection(callback: CallbackQuery, state: FSMContext):
        """Обработка выбора слота"""
        await callback.answer()
        
        if not booking_service:
            await callback.message.edit_text(
                "❌ Сервис бронирования недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Извлекаем datetime из callback_data
            datetime_start_str = callback.data.replace("slot_", "")
            start_time = parse_datetime_from_string(datetime_start_str)
            
            # Показываем индикатор во время поиска слотов
            async with TypingContext(callback.bot, callback.from_user.id):
                # Получаем все слоты для поиска выбранного (начиная со следующего дня)
                slots = calendar_service.get_free_slots(days=7, skip_today=True)
            selected_slot = None
            
            for slot in slots:
                if slot['datetime_start'] == datetime_start_str:
                    selected_slot = slot
                    break
            
            if not selected_slot:
                await callback.message.edit_text(
                    "❌ Этот слот больше не доступен. Пожалуйста, выберите другое время.",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Сохраняем выбранный слот в состоянии
            await state.update_data(selected_slot=selected_slot)
            
            # Создаем кнопки подтверждения
            confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")
                ]
            ])
            
            confirmation_text = (
                f"📝 Подтвердите бронирование:\n\n"
                f"📅 {selected_slot['day']}\n"
                f"⏰ {selected_slot['time']}\n\n"
                f"Нажмите 'Подтвердить' для записи."
            )
            
            await callback.message.edit_text(
                confirmation_text,
                reply_markup=confirm_keyboard
            )
            
            # Переходим в состояние подтверждения
            await state.set_state(BookingStates.confirming)
            
        except Exception as e:
            logger.error(f"Ошибка при выборе слота: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте выбрать время заново.",
                reply_markup=None
            )
            await state.clear()
    
    @router.callback_query(F.data == "confirm_booking", BookingStates.confirming)
    async def process_booking_confirmation(callback: CallbackQuery, state: FSMContext):
        """Обработка подтверждения бронирования"""
        await callback.answer()
        
        if not booking_service:
            await callback.message.edit_text(
                "❌ Сервис бронирования недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Получаем данные из состояния
            data = await state.get_data()
            selected_slot = data.get('selected_slot')
            
            if not selected_slot:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново с /book",
                    reply_markup=None
                )
                await state.clear()
                return
            
            start_time = selected_slot['start']
            end_time = selected_slot['end']
            
            user = callback.from_user
            user_name = user.first_name or ""
            user_contact = user.username or ""
            user_id = user.id
            
            # Показываем процесс бронирования
            await callback.message.edit_text(
                "⏳ Создаю бронирование...",
                reply_markup=None
            )
            
            # Создаем бронирование
            result = await booking_service.book_slot(
                start_time=start_time,
                end_time=end_time,
                user_name=user_name,
                user_contact=user_contact,
                user_id=user_id
            )
            
            # Очищаем состояние
            await state.clear()
            
            if result['success']:
                # Формируем сообщение об успехе
                success_text = (
                    f"✅ Бронирование успешно создано!\n\n"
                    f"📅 {selected_slot['day']}\n"
                    f"⏰ {selected_slot['time']}\n\n"
                    f"До встречи на пробном занятии! 🎉"
                )
                keyboard = create_main_menu_keyboard()
                reply_keyboard = get_main_reply_keyboard()
                await callback.message.edit_text(success_text, reply_markup=keyboard)
                await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
                
                # Уведомляем администраторов
                if config.ADMIN_IDS:
                    # Получаем бота из контекста
                    bot_instance = callback.bot
                    admin_message = (
                        f"📝 Новое бронирование:\n\n"
                        f"📅 {selected_slot['day']}\n"
                        f"⏰ {selected_slot['time']}\n"
                        f"👤 {user_name or 'Не указано'}\n"
                        f"📱 @{user_contact or 'Не указано'}\n"
                        f"🆔 {user.id}"
                    )
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await bot_instance.send_message(admin_id, admin_message)
                        except Exception as e:
                            logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
            else:
                error_text = (
                    f"❌ Не удалось создать бронирование.\n\n"
                    f"Причина: {result.get('error', 'Неизвестная ошибка')}\n\n"
                    f"Возможно, это время уже занято. Попробуйте выбрать другое время."
                )
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(error_text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Ошибка при подтверждении бронирования: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка при создании бронирования. Попробуйте позже.",
                reply_markup=keyboard
            )
            await state.clear()
    
    @router.callback_query(F.data == "refresh_slots")
    async def process_refresh_slots(callback: CallbackQuery, state: FSMContext):
        """Обновление списка слотов"""
        await callback.answer("🔄 Обновляю список...")
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Показываем индикатор во время поиска слотов
            async with TypingContext(callback.bot, callback.from_user.id):
                # Получаем свежие слоты (начиная со следующего дня)
                slots = calendar_service.get_free_slots(days=7, skip_today=True)
            
            if not slots:
                await callback.message.edit_text(
                    "😔 К сожалению, свободного времени не найдено.",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Создаем новую клавиатуру
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
            
            await state.set_state(BookingStates.selecting_slot)
            
        except Exception as e:
            # Игнорируем ошибку "message is not modified" - это нормально
            if "message is not modified" in str(e):
                await callback.answer()  # Подтверждаем callback
                return
            logger.error(f"Ошибка при обновлении слотов: {e}", exc_info=True)
            try:
                await callback.message.edit_text(
                    "❌ Произошла ошибка при обновлении. Попробуйте позже.",
                    reply_markup=None
                )
            except:
                await callback.answer("Ошибка при обновлении")
            await state.clear()
    
    @router.callback_query(F.data == "cancel_booking")
    async def process_cancel_booking(callback: CallbackQuery, state: FSMContext):
        """Отмена бронирования"""
        await callback.answer()
        keyboard = create_main_menu_keyboard()
        reply_keyboard = get_main_reply_keyboard()
        await callback.message.edit_text(
            "❌ Бронирование отменено.\n\n"
            "Используйте кнопки меню для новых действий.",
            reply_markup=keyboard
        )
        await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
        await state.clear()
    
    @router.callback_query(F.data == "back_to_menu")
    async def back_to_menu(callback: CallbackQuery, state: FSMContext):
        """Обработка кнопки 'Назад в меню'"""
        await callback.answer()
        await state.clear()
        
        user = callback.from_user
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я бот для записи на пробное занятие.\n\n"
            "Выберите действие из меню ниже 👇"
        )
        keyboard = create_main_menu_keyboard()
        reply_keyboard = get_main_reply_keyboard()
        await callback.message.edit_text(welcome_text, reply_markup=keyboard)
        await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
    
    # Обработчики FAQ
    @router.callback_query(F.data.in_(["faq_trial_lesson", "faq_courses", "faq_payment"]))
    async def handle_faq_topic(callback: CallbackQuery):
        """Обработчик кнопок FAQ"""
        from backend.keyboards.inline import get_faq_menu
        from backend.core.template_service import find_template_by_keywords, build_template_response
        from backend.db.database import get_full_parent_data
        
        await callback.answer()
        
        topic = callback.data
        user_id = callback.from_user.id
        username = callback.from_user.username
        
        # Маппинг callback_data на интенты шаблонов
        intent_map = {
            "faq_trial_lesson": "faq_trial_lesson",
            "faq_courses": "template_faq_courses",
            "faq_payment": "template_faq_payment"
        }
        
        intent = intent_map.get(topic)
        if not intent:
            await callback.message.edit_text(
                "К сожалению, я пока не нашел ответ на этот вопрос. Но я уже передал его менеджеру!",
                reply_markup=get_faq_menu()
            )
            return
        
        # Загружаем профиль пользователя для персонализации
        user_data = await get_full_parent_data(user_id, username) or {}
        
        # Ищем шаблон
        matched_intent, template = find_template_by_keywords(intent)
        
        if template:
            # Собираем ответ из шаблона
            response = await build_template_response(template, [], user_data)
            await callback.message.edit_text(response, reply_markup=get_faq_menu())
        else:
            await callback.message.edit_text(
                "К сожалению, я пока не нашел ответ на этот вопрос. Но я уже передал его менеджеру!",
                reply_markup=get_faq_menu()
            )
    
    # Обработчики меню
    @router.callback_query(F.data == "show_faq_menu")
    async def show_faq_menu(callback: CallbackQuery):
        """Показывает меню FAQ"""
        await callback.answer()
        await callback.message.edit_text(
            "Выберите интересующий вас вопрос из списка:",
            reply_markup=get_faq_menu()
        )
    
    @router.callback_query(F.data == "show_communities_menu")
    async def show_communities_menu(callback: CallbackQuery):
        """Показывает меню сообществ"""
        await callback.answer()
        await callback.message.edit_text(
            "🔗 Присоединяйтесь к нашим сообществам:",
            reply_markup=get_communities_menu()
        )
    
    # Регистрируем роутер
    dp.include_router(router)


