# backend/handlers/onboarding_handlers.py
"""
Telegram-handler для пошагового онбординга родителя и детей.
Обеспечивает надежное сохранение данных в БД.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from backend.states import GenericFSM, OnboardingFSM
from backend.utils.formatters import format_response_with_inflection
from backend.core.admin_notifications import notify_admin_on_error
from backend.db.database import (
    complete_onboarding_in_db,
    get_or_create_parent,
    add_child_profile,
    set_onboarding_step,
    save_dialog,
    save_parent_answers,
    load_dialog,
    get_full_parent_data,
)

router = Router()

async def start_fsm_scenario(message: types.Message, 
                             state: FSMContext, 
                             user_id: int, 
                             username: Optional[str], 
                             start_node: Optional[str] = None, 
                             intro_text: Optional[str] = None) -> None:
    """
    Начинает FSM-сценарий онбординга.
    Упрощенная версия без FSM_CONFIG - использует прямые состояния.
    """
    logging.info(f"[ОНБОРДИНГ] Запуск для пользователя {user_id}")
    
    # Создаем или получаем родителя
    parent = await get_or_create_parent(user_id, username)
    
    # Фиксируем время начала онбординга
    if not parent.onboarding_started_at:
        from backend.db.database import async_session_factory
        from sqlalchemy import update
        from backend.db.models import Parent
        
        async with async_session_factory() as session:
            await session.execute(
                update(Parent)
                .where(Parent.id == parent.id)
                .values(onboarding_started_at=datetime.now(timezone.utc).replace(tzinfo=None))
            )
            await session.commit()
        logging.info(f"[ОНБОРДИНГ] Зафиксировано время начала онбординга для Parent ID={parent.id}")
    
    # Начинаем с первого шага - имя родителя
    await state.set_state(OnboardingFSM.entering_parent_name)
    await state.update_data(user_answers={})
    
    if intro_text:
        await message.answer(intro_text)
    else:
        await message.answer(
            "Отлично! Давайте познакомимся. Это займет всего минуту.\n\n"
            "Как вас зовут?"
        )

@router.message(OnboardingFSM.entering_parent_name, F.text)
async def process_parent_name(message: types.Message, state: FSMContext):
    """Обработка имени родителя"""
    parent_name = message.text.strip()
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["parent_name"] = parent_name
    await state.update_data(user_answers=user_answers)
    await state.set_state(OnboardingFSM.entering_child_name)
    await message.answer(f"Приятно познакомиться, {parent_name}!\n\nКак зовут вашего ребенка?")

@router.message(OnboardingFSM.entering_child_name, F.text)
async def process_child_name(message: types.Message, state: FSMContext):
    """Обработка имени ребенка"""
    child_name = message.text.strip()
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["child_name"] = child_name
    await state.update_data(user_answers=user_answers)
    await state.set_state(OnboardingFSM.entering_child_age)
    await message.answer(f"Отлично! Сколько лет {child_name}?")

@router.message(OnboardingFSM.entering_child_age, F.text)
async def process_child_age(message: types.Message, state: FSMContext):
    """Обработка возраста ребенка"""
    try:
        child_age = int(message.text.strip())
        if child_age < 1 or child_age > 18:
            await message.answer("Пожалуйста, введите корректный возраст (от 1 до 18 лет).")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите возраст числом (например, 10).")
        return
    
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["child_age"] = child_age
    await state.update_data(user_answers=user_answers)
    await state.set_state(OnboardingFSM.entering_interests)
    await message.answer("Чем интересуется ваш ребенок? (например: игры, программирование, роботы)")

@router.message(OnboardingFSM.entering_interests, F.text)
async def process_interests(message: types.Message, state: FSMContext):
    """Обработка интересов ребенка"""
    interests = message.text.strip()
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["child_interests"] = interests
    await state.update_data(user_answers=user_answers)
    await state.set_state(OnboardingFSM.choose_contact_method)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📱 Телефон", callback_data="contact:phone"))
    builder.add(InlineKeyboardButton(text="📧 Email", callback_data="contact:email"))
    builder.add(InlineKeyboardButton(text="✈️ Telegram", callback_data="contact:telegram"))
    
    await message.answer(
        "Как с вами лучше связаться?",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("contact:"), OnboardingFSM.choose_contact_method)
async def process_contact_method(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора метода контакта"""
    method = callback.data.split(":")[1]
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["contact_method"] = method
    
    if method == "phone":
        await state.set_state(OnboardingFSM.entering_phone)
        await callback.message.edit_text("Введите ваш номер телефона:")
    elif method == "email":
        await state.set_state(OnboardingFSM.entering_email)
        await callback.message.edit_text("Введите ваш email:")
    else:  # telegram
        user_answers["parent_phone"] = None
        user_answers["parent_email"] = None
        user_answers["parent_contact_tg"] = f"@{callback.from_user.username}" if callback.from_user.username else "Telegram"
        await state.update_data(user_answers=user_answers)
        await finish_onboarding(callback.message, state, callback.from_user.id, callback.from_user.username)
    
    await callback.answer()

@router.message(OnboardingFSM.entering_phone, F.text)
async def process_phone(message: types.Message, state: FSMContext):
    """Обработка телефона"""
    phone = message.text.strip()
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["parent_phone"] = phone
    user_answers["parent_email"] = None
    user_answers["parent_contact_tg"] = None
    await state.update_data(user_answers=user_answers)
    await finish_onboarding(message, state, message.from_user.id, message.from_user.username)

@router.message(OnboardingFSM.entering_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    """Обработка email"""
    email = message.text.strip()
    data = await state.get_data()
    user_answers = data.get("user_answers", {})
    user_answers["parent_email"] = email
    user_answers["parent_phone"] = None
    user_answers["parent_contact_tg"] = None
    await state.update_data(user_answers=user_answers)
    await finish_onboarding(message, state, message.from_user.id, message.from_user.username)

async def finish_onboarding(message: types.Message, state: FSMContext, user_id: int, username: Optional[str]):
    """Завершает онбординг и сохраняет данные в БД"""
    logging.info(f"[ОНБОРДИНГ] Завершение сценария для пользователя {user_id}")
    data = await state.get_data()
    answers = data.get("user_answers", {})
    
    # Получаем родителя
    parent = await get_or_create_parent(user_id, username)
    
    # Определяем курс на основе возраста (упрощенная логика)
    child_age = answers.get("child_age", 0)
    if isinstance(child_age, str):
        try:
            child_age = int(child_age)
        except ValueError:
            child_age = 0
    
    if 9 <= child_age <= 13:
        course_name = "Основы программирования (младшая группа)"
    elif 14 <= child_age <= 17:
        course_name = "Продвинутое программирование (старшая группа)"
    else:
        course_name = "Программирование"
    
    # Сохраняем данные родителя
    full_name = answers.get("parent_name", "")
    phone = answers.get("parent_phone")
    email = answers.get("parent_email")
    
    # Сохраняем данные в user_data
    user_data = {
        "parent_name": full_name,
        "parent_phone": phone,
        "parent_email": email,
        "parent_contact_tg": answers.get("parent_contact_tg"),
        "child_name": answers.get("child_name"),
        "child_age": child_age,
        "child_interests": answers.get("child_interests"),
        "course_name": course_name
    }
    
    # Создаем профиль ребенка
    child = await add_child_profile(
        parent_id=parent.id,
        name=answers.get("child_name", "Ребенок"),
        age=child_age,
        interests=answers.get("child_interests"),
        course_name=course_name
    )
    
    # Завершаем онбординг в БД
    await complete_onboarding_in_db(
        parent_id=parent.id,
        full_name=full_name,
        phone=phone,
        email=email,
        user_data=user_data
    )
    
    # Отправляем финальное сообщение
    from backend.keyboards.inline import create_main_menu_keyboard
    await message.answer(
        f"Отлично, {full_name}! Мы сохранили ваши данные.\n\n"
        f"Ваш ребенок: {answers.get('child_name')}, {child_age} лет\n"
        f"Рекомендуемый курс: {course_name}\n\n"
        f"Теперь вы можете записаться на пробное занятие!",
        reply_markup=create_main_menu_keyboard()
    )
    
    await state.clear()
    logging.info(f"[ОНБОРДИНГ] Сценарий для пользователя {user_id} успешно завершен.")

