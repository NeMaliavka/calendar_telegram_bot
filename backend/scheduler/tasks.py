# backend/scheduler/tasks.py

import logging
import asyncio
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from backend.db.database import async_session_factory, get_lesson_by_id, is_time_slot_busy, update_trial_time, mark_lesson_completed
from backend.db.models import TrialLesson, TrialLessonStatus
from backend.utils.formatters import (
    format_response_with_inflection,
    format_date_russian,
    as_moscow_time,
    inflect_name
)

router = Router()
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


async def check_and_send_reminders(bot: Bot):
    """
    Проверяет уроки и отправляет напоминания за 24 часа и 1 час до начала.
    """
    logging.info("[SCHEDULER] Запуск проверки напоминаний...")

    # Текущее время в Москве
    now_msk = datetime.now(MOSCOW_TZ)

    # Окна напоминаний (в московском времени)
    window_24h_start = now_msk + timedelta(hours=23, minutes=50)
    window_24h_end   = now_msk + timedelta(hours=24, minutes=10)
    window_1h_start  = now_msk + timedelta(minutes=50)
    window_1h_end    = now_msk + timedelta(hours=1, minutes=10)
    
    def _as_aware_utc(dt):
        """Конвертирует naive datetime в aware UTC"""
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    async with async_session_factory() as session:
        # Предфильтр по верхней границе времени (UTC)
        now_utc = datetime.now(timezone.utc)
        wide_end_utc_aware = now_utc + timedelta(hours=25)
        wide_end_utc = wide_end_utc_aware.replace(tzinfo=None)

        planned_stmt = (
            select(TrialLesson)
            .where(
                TrialLesson.status == TrialLessonStatus.PLANNED,
                TrialLesson.scheduled_at <= wide_end_utc
            )
            .options(
                selectinload(TrialLesson.parent),
                selectinload(TrialLesson.child),
            )
        )
        
        planned_result = await session.execute(planned_stmt)
        planned_lessons = planned_result.scalars().all()

        tasks_to_run = []
        lessons_to_process = []

        for lesson in planned_lessons:
            scheduled_utc = _as_aware_utc(lesson.scheduled_at)
            scheduled_msk = scheduled_utc.astimezone(MOSCOW_TZ)

            in_window_24h = (window_24h_start <= scheduled_msk <= window_24h_end) and (not lesson.reminder_24h_sent)
            in_window_1h  = (window_1h_start  <= scheduled_msk <= window_1h_end)  and (not lesson.reminder_1h_sent)

            if in_window_24h:
                logging.info(f"24ч окно: урок {lesson.id} на {scheduled_msk}")
                tasks_to_run.append(send_reminder_message(bot, lesson, "завтра"))
                lessons_to_process.append((lesson, "24h"))

            elif in_window_1h:
                logging.info(f"1ч окно: урок {lesson.id} на {scheduled_msk}")
                tasks_to_run.append(send_reminder_message(bot, lesson, "через час"))
                lessons_to_process.append((lesson, "1h"))

        if not tasks_to_run:
            logging.info("[SCHEDULER] Найдены уроки, но нет подходящих по времени.")
            return

        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)

        successful_ids_24h, successful_ids_1h = [], []
        for i, result in enumerate(results):
            lesson, reminder_type = lessons_to_process[i]
            if not isinstance(result, Exception):
                if reminder_type == "24h":
                    successful_ids_24h.append(lesson.id)
                else:
                    successful_ids_1h.append(lesson.id)
            else:
                logging.error(f"Не удалось отправить {reminder_type} напоминание для урока {lesson.id}: {result}")

        if successful_ids_24h:
            await session.execute(
                update(TrialLesson).where(TrialLesson.id.in_(successful_ids_24h)).values(reminder_24h_sent=True)
            )
        if successful_ids_1h:
            await session.execute(
                update(TrialLesson).where(TrialLesson.id.in_(successful_ids_1h)).values(reminder_1h_sent=True)
            )

        if successful_ids_24h or successful_ids_1h:
            await session.commit()
            logging.info(f"[SCHEDULER] Обновлены флаги: 24ч={len(successful_ids_24h)}, 1ч={len(successful_ids_1h)}.")

    await check_completed_lessons(bot)


async def send_reminder_message(bot: Bot, lesson: TrialLesson, when: str):
    """Отправляет напоминание родителю о предстоящем уроке"""
    parent = lesson.parent
    child = lesson.child    
    moscow_time = as_moscow_time(lesson.scheduled_at.replace(tzinfo=timezone.utc) if lesson.scheduled_at.tzinfo is None else lesson.scheduled_at)
    lesson_time_str = moscow_time.strftime('%H:%M')
    child_name_safe = child.name if child else "вашего ребёнка"
    
    reminder_template = [
        ("👋 Здравствуйте, {parent_name_vocative}!\n\n"
         "Напоминаем, что пробный урок для {child_name:gent} состоится {when} в {lesson_time_str} (по московскому времени).\n\n"
         "Если Ваши планы изменились, то перенесите или отмените запись, чтобы наши педагоги смогли вовремя начать занятие. "
         "Желаем плодотворного урока!🧡\n"
         "С уважением, команда школы"),
        ("👋 Добрый день, {parent_name_vocative}!\n\n"
         "Уже совсем скоро — пробный урок для {child_name:gent}:"
         "📅 {when}, 🕓 {lesson_time_str} (время московское).\n\n"
         "Если планы поменялись — дайте нам знать."
         "Мы с радостью подберём другое время 😊\n"
         "Пусть занятие пройдёт с интересом и пользой!\n"
         "С теплом, команда"),
        ("👋 Здравствуйте, {parent_name_vocative}!\n\n"
         "Напоминаем: пробный урок для {child_name:gent} состоится {when} в {lesson_time_str} (МСК).\n\n"
         "Если необходимо — вы можете перенести или отменить занятие.\n"
         "Спасибо, что с нами!\n"
         "С уважением, команда\n"),
        ("👋 {parent_name_vocative}, добрый день!\n\n"
         "Мы ждём {child_name:accs} на пробный урок {when} в {lesson_time_str} (по Москве).\n\n"
         "Если что-то изменилось — напишите нам, и мы найдём удобное время.\n"
         "Пусть этот урок станет первым шагом в мир программирования! 💻\n"
         "С уважением, команда")
    ]
    
    data_for_template = {
        "parent_name_vocative": parent.full_name or "уважаемый родитель",
        "child_name": child_name_safe,
        "when": when,
        "lesson_time_str": lesson_time_str
    }
    
    text = format_response_with_inflection(random.choice(reminder_template), data_for_template)
    
    # Создаем простую клавиатуру для напоминания
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔄 Перенести",
        callback_data=f"reschedule_lesson:{lesson.id}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Отменить",
        callback_data=f"cancel_lesson:{lesson.id}"
    ))
    keyboard = builder.as_markup()
    
    try:
        await bot.send_message(parent.telegram_id, text, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Не удалось отправить напоминание пользователю {parent.telegram_id} для урока {lesson.id}: {e}")


async def check_completed_lessons(bot: Bot):
    """
    Проверяет завершенные уроки и обновляет их статус в БД.
    Урок считается завершенным, если его время прошло более чем на 1 час.
    """
    logging.info("[SCHEDULER] Запуск проверки завершенных уроков")
    
    now_utc = datetime.now(timezone.utc)
    # Уроки, которые начались более часа назад
    cutoff_time = (now_utc - timedelta(hours=1)).replace(tzinfo=None)

    async with async_session_factory() as session:
        stmt = (
            select(TrialLesson)
            .where(
                TrialLesson.status == TrialLessonStatus.PLANNED,
                TrialLesson.scheduled_at <= cutoff_time
            )
            .options(
                selectinload(TrialLesson.parent),
                selectinload(TrialLesson.child),
            )
        )
        
        result = await session.execute(stmt)
        completed_lessons = result.scalars().all()
        
        for lesson in completed_lessons:
            try:
                updated_lesson = await mark_lesson_completed(session, lesson.id)
                if updated_lesson:
                    logging.info(f"[SCHEDULER] Урок ID={lesson.id} отмечен как завершенный")
                    # Здесь можно добавить запрос отзыва, если нужно
            except Exception as e:
                logging.error(f"[SCHEDULER] Ошибка при обновлении статуса урока ID={lesson.id}: {e}")

