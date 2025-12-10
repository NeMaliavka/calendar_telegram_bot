# backend/handlers/waitlist_handlers.py

import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from backend.states import WaitlistFSM
from backend.db.database import add_waitlist_entry, get_or_create_parent, get_full_parent_data

router = Router()

@router.callback_query(F.data == "waitlist:join")
async def handle_waitlist_join(callback: types.CallbackQuery, state: FSMContext):
    """
    Шаг 1: Пользователь выбрал «сообщить о запуске курса» — запрашиваем контакт.
    """
    logging.info(f"[WAITLIST] User {callback.from_user.id} clicked waitlist:join")
    await callback.message.edit_text(
        "Отлично! Пожалуйста, оставьте ваш номер телефона или email, и мы сообщим о запуске курса."
    )
    await state.set_state(WaitlistFSM.waiting_for_contact)
    await callback.answer()

@router.callback_query(F.data == "waitlist:cancel")
async def handle_waitlist_cancel(callback: types.CallbackQuery, state: FSMContext):
    """
    Шаг отмены: пользователь передумал — завершаем сценарий листа ожидания.
    """
    logging.info(f"[WAITLIST] User {callback.from_user.id} canceled waitlist")
    await state.clear()
    
    from backend.keyboards.inline import create_main_menu_keyboard
    await callback.message.edit_text(
        "Понял вас. Если передумаете, всегда на связи! 😊",
        reply_markup=create_main_menu_keyboard()
    )
    await callback.answer()

@router.message(WaitlistFSM.waiting_for_contact, F.text)
async def process_waitlist_contact(message: types.Message, state: FSMContext):
    """
    Обрабатывает контактные данные для листа ожидания.
    Сохраняет в БД без создания сделки в Bitrix.
    """
    contact = message.text.strip()
    user_id = message.from_user.id
    
    # Получаем полный профиль, чтобы знать внутренний ID родителя
    full_data = await get_full_parent_data(user_id, message.from_user.username)
    if not full_data:
        await message.answer("Произошла ошибка, не смог найти ваш профиль. Пожалуйста, попробуйте снова.")
        return

    parent_id = full_data.get('id')
    
    # Извлекаем все накопленные в FSM данные
    fsm_data = await state.get_data()
    user_answers = fsm_data.get('user_answers', {})
    
    # Определяем возрастную группу
    child_age = user_answers.get('child_age', 'N/A')
    age_group = f"<{child_age}" if isinstance(child_age, (int, str)) and str(child_age).isdigit() else "unknown"
    
    # Сохраняем запись в БД (без deal_id, так как Bitrix не используется)
    await add_waitlist_entry(
        parent_id=parent_id,
        contact=contact,
        age_group=age_group,
        deal_id=None  # Bitrix не используется
    )
    
    # Благодарим пользователя и завершаем сценарий
    from backend.keyboards.inline import create_main_menu_keyboard
    await message.answer(
        "Спасибо! Мы сохранили ваши данные и обязательно сообщим вам о старте курса. 🎉",
        reply_markup=create_main_menu_keyboard()
    )
    await state.clear()

