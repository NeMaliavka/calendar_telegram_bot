"""
Обработчики для переноса и отмены записей
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
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
from backend.utils import parse_datetime_from_string
from backend.utils.typing_indicator import TypingContext

logger = logging.getLogger(__name__)

router = Router()


def setup_reschedule_cancel_handlers(
    dp,
    calendar_service: CalendarService,
    booking_service: BookingService
):
    """
    Настраивает обработчики переноса и отмены
    
    Args:
        dp: Dispatcher
        calendar_service: Сервис календаря
        booking_service: Сервис бронирования
    """
    
    # ========== Обработчики переноса ==========
    
    @router.callback_query(F.data.startswith("reschedule_"), BookingStates.selecting_event_to_reschedule)
    async def process_event_selection_for_reschedule(callback: CallbackQuery, state: FSMContext):
        """Обработка выбора записи для переноса"""
        await callback.answer()
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Извлекаем ID события
            event_id = callback.data.replace("reschedule_", "")
            
            # Получаем данные из состояния
            data = await state.get_data()
            events = data.get('events', [])
            
            # Находим выбранное событие
            selected_event = None
            for event in events:
                if event.get('id') == event_id:
                    selected_event = event
                    break
            
            if not selected_event:
                await callback.message.edit_text(
                    "❌ Запись не найдена. Попробуйте снова с /reschedule",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Сохраняем выбранное событие
            await state.update_data(selected_event=selected_event)
            
            # Получаем доступные слоты
            await callback.message.edit_text("🔍 Ищу доступное время...")
            
            # Показываем индикатор во время поиска слотов
            async with TypingContext(callback.bot, callback.from_user.id):
                slots = calendar_service.get_free_slots(days=7, skip_today=True)
            
            if not slots:
                await callback.message.edit_text(
                    "😔 К сожалению, нет доступного времени для переноса.",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Создаем клавиатуру с доступными слотами
            keyboard = create_slots_keyboard(slots, max_slots=30)
            # Добавляем кнопку "Назад в меню"
            keyboard.inline_keyboard = add_back_to_menu_button(keyboard.inline_keyboard)
            
            message_text = (
                f"📅 Перенос записи:\n"
                f"Текущее время: {selected_event['day']} {selected_event['time']}\n\n"
                f"Выберите новое время:\n"
                f"Найдено {len(slots)} свободных слотов."
            )
            
            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )
            
            await state.set_state(BookingStates.rescheduling)
            
        except Exception as e:
            logger.error(f"Ошибка при выборе записи для переноса: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте снова.",
                reply_markup=None
            )
            await state.clear()
    
    @router.callback_query(F.data.startswith("slot_"), BookingStates.rescheduling)
    async def process_slot_selection_for_reschedule(callback: CallbackQuery, state: FSMContext):
        """Обработка выбора нового времени при переносе"""
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
            
            # Получаем данные из состояния
            data = await state.get_data()
            selected_event = data.get('selected_event')
            
            if not selected_event:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново с /reschedule",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Показываем индикатор во время поиска слотов
            async with TypingContext(callback.bot, callback.from_user.id):
                # Получаем все слоты для поиска выбранного
                slots = calendar_service.get_free_slots(days=7, skip_today=True)
            new_slot = None
            
            for slot in slots:
                if slot['datetime_start'] == datetime_start_str:
                    new_slot = slot
                    break
            
            if not new_slot:
                await callback.message.edit_text(
                    "❌ Этот слот больше не доступен. Пожалуйста, выберите другое время.",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Сохраняем новый слот
            await state.update_data(new_slot=new_slot)
            
            # Создаем кнопки подтверждения
            confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить перенос", callback_data="confirm_reschedule"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reschedule")
                ]
            ])
            
            confirmation_text = (
                f"📝 Подтвердите перенос записи:\n\n"
                f"❌ Отменить:\n"
                f"📅 {selected_event['day']}\n"
                f"⏰ {selected_event['time']}\n\n"
                f"✅ Перенести на:\n"
                f"📅 {new_slot['day']}\n"
                f"⏰ {new_slot['time']}\n\n"
                f"Нажмите 'Подтвердить перенос' для выполнения."
            )
            
            await callback.message.edit_text(
                confirmation_text,
                reply_markup=confirm_keyboard
            )
            
            await state.set_state(BookingStates.confirming)
            
        except Exception as e:
            logger.error(f"Ошибка при выборе времени для переноса: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте выбрать время заново.",
                reply_markup=None
            )
            await state.clear()
    
    @router.callback_query(F.data == "confirm_reschedule", BookingStates.confirming)
    async def process_reschedule_confirmation(callback: CallbackQuery, state: FSMContext):
        """Обработка подтверждения переноса"""
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
            selected_event = data.get('selected_event')
            new_slot = data.get('new_slot')
            
            if not selected_event or not new_slot:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново с /reschedule",
                    reply_markup=None
                )
                await state.clear()
                return
            
            start_time = new_slot['start']
            end_time = new_slot['end']
            event_id_to_cancel = selected_event.get('id')
            
            user = callback.from_user
            user_name = user.first_name or ""
            user_contact = user.username or ""
            user_id = user.id
            
            # Показываем процесс переноса
            await callback.message.edit_text(
                "⏳ Переношу запись...",
                reply_markup=None
            )
            
            # Получаем информацию о старой записи для примечания
            old_event_info = f"{selected_event['day']} {selected_event['time']}"
            
            # Создаем новую запись с отменой старой
            result = await booking_service.book_slot(
                start_time=start_time,
                end_time=end_time,
                user_name=user_name,
                user_contact=user_contact,
                user_id=user_id,
                cancel_event_id=event_id_to_cancel
            )
            
            # Обновляем статус старой записи в таблице на "Перенесена"
            if result['success'] and booking_service.sheets_service and event_id_to_cancel:
                try:
                    new_event_info = f"{new_slot['day']} {new_slot['time']}"
                    note = f"Перенесено на: {new_event_info}"
                    booking_service.sheets_service.update_booking_status(
                        event_id=event_id_to_cancel,
                        new_status="Перенесена",
                        note=note
                    )
                except Exception as e:
                    logger.error(f"Ошибка при обновлении статуса старой записи: {e}", exc_info=True)
            
            # Очищаем состояние
            await state.clear()
            
            if result['success']:
                success_text = (
                    f"✅ Запись успешно перенесена!\n\n"
                    f"❌ Отменено:\n"
                    f"📅 {selected_event['day']}\n"
                    f"⏰ {selected_event['time']}\n\n"
                    f"✅ Новое время:\n"
                    f"📅 {new_slot['day']}\n"
                    f"⏰ {new_slot['time']}\n\n"
                    f"До встречи на пробном занятии! 🎉"
                )
                keyboard = create_main_menu_keyboard()
                reply_keyboard = get_main_reply_keyboard()
                await callback.message.edit_text(success_text, reply_markup=keyboard)
                await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
            else:
                error_text = (
                    f"❌ Не удалось перенести запись.\n\n"
                    f"Причина: {result.get('error', 'Неизвестная ошибка')}\n\n"
                    f"Попробуйте выбрать другое время."
                )
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(error_text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Ошибка при подтверждении переноса: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка при переносе записи. Попробуйте позже.",
                reply_markup=keyboard
            )
            await state.clear()
    
    @router.callback_query(F.data == "cancel_reschedule")
    async def process_cancel_reschedule(callback: CallbackQuery, state: FSMContext):
        """Отмена переноса"""
        await callback.answer()
        keyboard = create_main_menu_keyboard()
        await callback.message.edit_text(
            "❌ Перенос отменен.\n\n"
            "Используйте кнопки меню для новых действий.",
            reply_markup=keyboard
        )
        await state.clear()
    
    # ========== Обработчики отмены ==========
    
    @router.callback_query(F.data.startswith("cancel_event_"), BookingStates.selecting_event_to_cancel)
    async def process_event_selection_for_cancel(callback: CallbackQuery, state: FSMContext):
        """Обработка выбора записи для отмены"""
        await callback.answer()
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Извлекаем ID события
            event_id = callback.data.replace("cancel_event_", "")
            
            # Получаем данные из состояния
            data = await state.get_data()
            events = data.get('events', [])
            
            # Находим выбранное событие
            selected_event = None
            for event in events:
                if event.get('id') == event_id:
                    selected_event = event
                    break
            
            if not selected_event:
                await callback.message.edit_text(
                    "❌ Запись не найдена. Попробуйте снова с /cancel",
                    reply_markup=None
                )
                await state.clear()
                return
            
            # Сохраняем выбранное событие
            await state.update_data(selected_event=selected_event)
            
            # Создаем кнопки подтверждения
            confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, отменить", callback_data="confirm_cancel"),
                    InlineKeyboardButton(text="❌ Нет", callback_data="cancel_cancel")
                ]
            ])
            
            confirmation_text = (
                f"⚠️ Вы уверены, что хотите отменить запись?\n\n"
                f"📅 {selected_event['day']}\n"
                f"⏰ {selected_event['time']}\n\n"
                f"После отмены запись будет удалена из календаря."
            )
            
            await callback.message.edit_text(
                confirmation_text,
                reply_markup=confirm_keyboard
            )
            
            await state.set_state(BookingStates.confirming)
            
        except Exception as e:
            logger.error(f"Ошибка при выборе записи для отмены: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ Произошла ошибка. Попробуйте снова.",
                reply_markup=None
            )
            await state.clear()
    
    @router.callback_query(F.data == "confirm_cancel", BookingStates.confirming)
    async def process_cancel_confirmation(callback: CallbackQuery, state: FSMContext):
        """Обработка подтверждения отмены"""
        await callback.answer()
        
        if not calendar_service:
            await callback.message.edit_text(
                "❌ Сервис календаря недоступен.",
                reply_markup=None
            )
            await state.clear()
            return
        
        try:
            # Получаем данные из состояния
            data = await state.get_data()
            selected_event = data.get('selected_event')
            
            if not selected_event:
                await callback.message.edit_text(
                    "❌ Сессия истекла. Начните заново с /cancel",
                    reply_markup=None
                )
                await state.clear()
                return
            
            event_id = selected_event.get('id')
            
            # Показываем процесс отмены
            await callback.message.edit_text(
                "⏳ Отменяю запись...",
                reply_markup=None
            )
            
            # Удаляем событие через booking_service (чтобы обновить таблицу)
            if booking_service:
                success = await booking_service.cancel_booking(event_id)
            else:
                success = calendar_service.delete_event(event_id)
            
            # Очищаем состояние
            await state.clear()
            
            if success:
                success_text = (
                    f"✅ Запись успешно отменена!\n\n"
                    f"📅 {selected_event['day']}\n"
                    f"⏰ {selected_event['time']}\n\n"
                    f"Запись удалена из календаря."
                )
                keyboard = create_main_menu_keyboard()
                reply_keyboard = get_main_reply_keyboard()
                await callback.message.edit_text(success_text, reply_markup=keyboard)
                await callback.message.answer("Или используйте боковое меню:", reply_markup=reply_keyboard)
            else:
                error_text = (
                    f"❌ Не удалось отменить запись.\n\n"
                    f"Попробуйте снова."
                )
                keyboard = create_main_menu_keyboard()
                await callback.message.edit_text(error_text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Ошибка при подтверждении отмены: {e}", exc_info=True)
            keyboard = create_main_menu_keyboard()
            await callback.message.edit_text(
                "❌ Произошла ошибка при отмене записи. Попробуйте позже.",
                reply_markup=keyboard
            )
            await state.clear()
    
    @router.callback_query(F.data == "cancel_cancel")
    async def process_cancel_cancel(callback: CallbackQuery, state: FSMContext):
        """Отмена процесса отмены записи"""
        await callback.answer()
        keyboard = create_main_menu_keyboard()
        await callback.message.edit_text(
            "❌ Отмена записи отменена.\n\n"
            "Используйте кнопки меню для новых действий.",
            reply_markup=keyboard
        )
        await state.clear()
    
    # Регистрируем роутер
    dp.include_router(router)

