# backend/handlers/check_booking_handlers.py
"""
Обработчик для проверки статуса записи на пробный урок (/my_lessons).
Использует get_full_parent_data для эффективной и надежной работы.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from backend.db.database import get_full_parent_data, utc_naive_to_moscow
from backend.db.models import TrialLessonStatus
from backend.utils.formatters import format_date_russian

router = Router()

def format_lesson_time(lesson_time) -> str:
    """
    Принимает datetime (naive/aware) или строку ISO из БД,
    переводит UTC-naive в московское время и возвращает строку для пользователя.
    """
    if isinstance(lesson_time, str):
        try:
            from backend.utils.formatters import parse_datetime_iso
            dt = parse_datetime_iso(lesson_time)
        except Exception:
            logging.warning(f"[ВРЕМЯ] Не удалось распарсить время: {lesson_time}")
            return "неизвестно"
    else:
        dt = lesson_time

    msk_time = utc_naive_to_moscow(dt) if dt else None
    return format_date_russian(msk_time, 'full') if msk_time else "неизвестно"

def get_active_lessons(full_data: dict) -> list:
    """Извлекает активные уроки из данных родителя"""
    lessons = full_data.get('trial_lessons', [])
    return [
        lesson for lesson in lessons 
        if lesson.get('status') == TrialLessonStatus.PLANNED.name
    ]

async def start_check_booking_flow(message: types.Message, 
                                   state: FSMContext, 
                                   user_id: int, 
                                   username: Optional[str]):
    """Проверяет записи пользователя из БД"""
    await state.clear()
    logging.info(f"[ПРОВЕРКА ЗАПИСИ] Запуск для пользователя {username} {user_id}")

    full_data = await get_full_parent_data(user_id, username)

    if not full_data or not full_data.get("onboarding_completed_at"):
        logging.info(f"[ПРОВЕРКА ЗАПИСИ] Пользователь {user_id} не проходил онбординг, предлагаем анкету.")
        from backend.keyboards.inline import create_main_menu_keyboard
        await message.answer(
            "Чтобы я мог показать ваши записи, мне нужно сначала с вами познакомиться. Это займет всего минуту.",
            reply_markup=create_main_menu_keyboard()
        )
        return

    active_lessons = get_active_lessons(full_data)
    if not active_lessons:
        from backend.keyboards.inline import create_main_menu_keyboard
        await message.answer(
            "Я проверил, но пока не нашел у вас запланированных уроков. Может, запишемся на пробное занятие?",
            reply_markup=create_main_menu_keyboard()
        )
        return

    from backend.keyboards.inline import create_main_menu_keyboard
    keyboard = create_main_menu_keyboard()

    children_map = {
        str(child.get('id')): child.get('name', 'вашего ребенка')
        for child in full_data.get("children", [])
    }

    if len(active_lessons) == 1:
        lesson = active_lessons[0]
        child_name = children_map.get(str(lesson.get('child_id')), 'вашего ребенка')
        lesson_time_str = format_lesson_time(lesson.get('scheduled_at'))

        await message.answer(
            f"Да, конечно! Нашел вашу запись. ✅\n\n"
            f"Пробный урок для {child_name} запланирован на {lesson_time_str}.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        response_text = "Да, у вас есть несколько активных записей:"
        for i, lesson in enumerate(active_lessons, 1):
            child_name = children_map.get(str(lesson.get('child_id')), 'вашего ребенка')
            lesson_time_str = format_lesson_time(lesson.get('scheduled_at'))
            
            response_text += f"\n\n{i}. Пробный урок: <b>{child_name}</b> на <b>{lesson_time_str}</b>"

        await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "check_booking")
async def handle_check_booking_callback(callback: types.CallbackQuery, 
                                        state: FSMContext):
    await callback.answer("Проверяю ваше расписание...")
    await callback.message.edit_text("Один момент...")
    await start_check_booking_flow(
        message=callback.message,
        state=state,
        user_id=callback.from_user.id,
        username=callback.from_user.username
    )

@router.message(F.text == "/my_lessons")
async def handle_my_lessons_command(message: types.Message, 
                                    state: FSMContext):
    await start_check_booking_flow(
        message=message,
        state=state,
        user_id=message.from_user.id,
        username=message.from_user.username
    )

