# backend/handlers/sales_funnel.py
"""
Главный роутер, "мозг" бота. Отвечает за команду /start,
распознавание интентов и маршрутизацию пользователя.
"""

import logging
import re
from typing import Optional, List, Dict, Union

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatAction

from backend.db.database import (
    get_full_parent_data, 
    save_dialog, 
    load_dialog, 
    increment_irrelevant_count, 
    block_user, 
    get_or_create_parent
)
from backend.states import GenericFSM
from backend.core.template_service import find_template_by_keywords, build_template_response
from backend.core.admin_notifications import notify_admin_of_request, notify_admin_on_error, notify_admin_of_block
from backend.handlers.onboarding_handlers import start_fsm_scenario
from backend.utils.text_tools import correct_keyboard_layout
from backend.core.llm_service import get_llm_response, is_query_relevant_with_layout_correction
from backend.services.rag_service import find_contextual_answer
from backend.services.intent_recognizer import IntentRecognizer
from backend.utils.typing_indicator import TypingContext

router = Router()
IRRELEVANT_QUERY_LIMIT = 3

command_map = {
    "START_ENROLLMENT": ("Записаться на пробное занятие", "start_booking"),
    "CANCEL_BOOKING": ("Отменить урок", "initiate_cancellation"),
    "RESCHEDULE_BOOKING": ("Перенести урок", "initiate_reschedule"),
}

# Определяем мапу интентов (упрощенная версия)
async def handle_booking_intent(message, state, user_id, username):
    """Обработчик интента бронирования"""
    await start_booking_scenario(message, state, user_id, username)

intent_to_action = {
    "booking": handle_booking_intent,
    # Другие интенты можно добавить позже
}

async def show_greeting_screen(message: types.Message, 
                               state: FSMContext, 
                               user_id: int,
                               username: Optional[str]):
    """
    Показывает приветственный экран. Логика полностью основана на get_full_parent_data.
    """
    await state.clear()
    logging.info(f"[ГЛАВНЫЙ ЭКРАН] Показываем приветствие для пользователя {user_id}")

    full_data = await get_full_parent_data(user_id, username)

    # Сценарий 1: Новый пользователь, который еще не проходил онбординг
    if not full_data or not full_data.get("onboarding_completed_at"):
        logging.info(f"[ГЛАВНЫЙ ЭКРАН] Пользователь {user_id} - новый. Показываем приглашение к онбордингу.")
        from backend.keyboards.inline import create_main_menu_keyboard
        await message.answer(
            "👋 Здравствуйте! Я — ваш персональный менеджер в школе программирования.\n\n"
            "Я здесь, чтобы помочь вам выбрать идеальный курс для вашего ребенка и записать его на бесплатный пробный урок.\n\n"
            "Чтобы начать, давайте познакомимся?",
            reply_markup=create_main_menu_keyboard()
        )
    # Сценарий 2: Пользователь уже прошел онбординг
    else:
        from backend.db.models import TrialLessonStatus
        active_lessons = [
            lesson for lesson in full_data.get("trial_lessons", []) 
            if lesson.get("status") == TrialLessonStatus.PLANNED.name
        ]
        has_lessons = bool(active_lessons)
        
        from backend.keyboards.inline import create_main_menu_keyboard
        keyboard = create_main_menu_keyboard()
        
        user_data = full_data.get("user_data", {})
        parent_name = user_data.get("parent_name", "уважаемый родитель")
        
        logging.info(f"[ГЛАВНЫЙ ЭКРАН] Пользователь {parent_name} - существующий. Показываем главное меню.")
        await message.answer(
            f"Рад вас снова видеть, {parent_name}! Чем могу сегодня помочь?",
            reply_markup=keyboard
        )

@router.message(Command("start"))
async def handle_start(message: types.Message, state: FSMContext):
    logging.info(f"[ГЛАВНЫЙ ЭКРАН] Пользователь {message.from_user.id} нажал /start")
    await show_greeting_screen(
        message, 
        state, 
        user_id=message.from_user.id,
        username=message.from_user.username
    )

@router.message(F.text)
async def handle_text_message(message: types.Message, 
                              state: FSMContext, 
                              bot: Bot):
    """
    Умный обработчик текстовых сообщений:
    1. Проверяет, прошел ли пользователь онбординг. Если нет - отправляет на него.
    2. Если да - распознает интент и дает персонализированный ответ с меню.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    user_text = message.text
    logging.info(f"Обработка сообщения от {user_id}. Текст: '{user_text}'")

    try:
        # Получаем полный профиль клиента
        user_profile = await get_full_parent_data(user_id, username)
        
        # Если БД недоступна, создаем минимальный профиль для работы
        if not user_profile:
            logging.warning(f"БД недоступна для пользователя {user_id}. Работаем в режиме без БД.")
            user_profile = {
                "id": None,
                "telegram_id": user_id,
                "username": username,
                "is_blocked": False,
                "onboarding_completed_at": None,
                "user_data": {},
                "children": [],
                "trial_lessons": []
            }
        
        # Проверки-"охранники"
        if user_profile.get("is_blocked"):
            logging.warning(f"Заблокированный пользователь {user_id} пытался отправить сообщение.")
            return

        if not user_profile.get("onboarding_completed_at"):
            logging.info(f"Пользователь {user_id} не прошел онбординг. Показываем приглашение.")
            from backend.keyboards.inline import create_main_menu_keyboard
            await message.answer(
                "Рад знакомству! Чтобы я мог вам помочь, давайте для начала познакомимся. Это займет всего минуту.",
                reply_markup=create_main_menu_keyboard()
            )
            return

        # Основная логика
        history = await load_dialog(user_id)
        parent = await get_or_create_parent(user_id, username)
        if parent:
            await save_dialog(parent.id, "user", user_text)

        # Получаем intent_recognizer из bot (если доступен)
        intent_recognizer = getattr(bot, 'intent_recognizer', None)
        detected_intent = None
        if intent_recognizer:
            # Показываем индикатор во время распознавания интента
            async with TypingContext(bot, user_id):
                detected_intent = intent_recognizer.recognize(user_text)
            logging.info(f"Для Parent ID={user_profile.get('id')} распознано намерение: {detected_intent}")
            
            # Если распознан интент, который требует действия
            if detected_intent in intent_to_action:
                await intent_to_action[detected_intent](message, state, user_id, username)
                if parent:
                    await save_dialog(parent.id, "assistant", f"Распознан интент: {detected_intent}")
                return

        # Получаем retriever из bot (если доступен)
        retriever = getattr(bot, 'retriever', None)

        from backend.keyboards.inline import create_main_menu_keyboard
        keyboard = create_main_menu_keyboard()

        # Поиск ответа по базе знаний (Шаблоны и RAG)
        _intent, template = find_template_by_keywords(detected_intent or user_text)
        if template:
            response = await build_template_response(template, history, user_profile.get("user_data", {}))
            await message.answer(response, reply_markup=keyboard)
            if parent:
                await save_dialog(parent.id, "assistant", response)
            return

        # Проверка на релевантность и RAG-поиск
        async with TypingContext(bot, user_id):
            is_relevant = await is_query_relevant_with_layout_correction(user_text, history)
        
        if not is_relevant:
            logging.warning(f"Запрос от пользователя {user_id} отмечен как нерелевантный.")
            new_irrelevant_count = await increment_irrelevant_count(user_id, username)

            if new_irrelevant_count == 1:
                await message.answer(
                    "Хм, кажется, этот вопрос не совсем по моей теме. Я — AI-менеджер школы и лучше всего разбираюсь в курсах по программированию для детей и подростков. 😊\n\n"
                    "Могу рассказать о программе, стоимости или помочь записаться на бесплатный пробный урок. С чего начнем?",
                    reply_markup=keyboard
                )
            elif new_irrelevant_count < IRRELEVANT_QUERY_LIMIT:
                builder = InlineKeyboardBuilder()
                builder.button(text="☎️ Позвать менеджера", callback_data="request_manager")
                await message.answer(
                    "Я снова не уверен, что правильно вас понимаю. Моя главная задача — помогать с нашими курсами программирования. 🤖\n\n"
                    "Возможно, ваш вопрос лучше задать живому менеджеру? Я могу сразу передать ему наш диалог.",
                    reply_markup=builder.as_markup()
                )
            elif new_irrelevant_count >= IRRELEVANT_QUERY_LIMIT:
                logging.warning(f"Блокировка пользователя {user_id} из-за повторяющихся нерелевантных запросов.")
                await block_user(user_profile.get('id'))
                await message.answer(
                    "Кажется, я не справляюсь с вашим вопросом. Чтобы вы не тратили время, я уже позвал на помощь нашего менеджера. "
                    "Он скоро подключится прямо к этому чату и обязательно вам поможет! 👌"
                )
                await notify_admin_of_block(
                    bot=bot, 
                    user=message.from_user, 
                    history=history, 
                    reason="Клиент задал несколько вопросов не по теме, AI-помощник не справился."
                )
            return

        # Если вопрос релевантен, но прямого ответа нет - используем RAG
        if retriever:
            logging.info(f"Точный шаблон не найден, запускаем RAG-поиск для пользователя {user_id}.")
            # Показываем индикатор во время RAG поиска (это может занять время)
            async with TypingContext(bot, user_id):
                rag_answer = await find_contextual_answer(user_text, history, retriever=retriever)
            
            if rag_answer:
                # Проверяем наличие управляющих команд в ответе
                all_commands_in_answer = re.findall(r'\[([A-Z_]+)\]', rag_answer)
                commands_in_answer = list(set(all_commands_in_answer))
                
                if len(commands_in_answer) == 1:
                    cmd = commands_in_answer[0]
                    clean_answer = re.sub(r"\[[A-Z_]+\]", "", rag_answer).strip()
                    
                    if clean_answer:
                        await message.answer(clean_answer)
                    
                    if cmd == "START_ENROLLMENT":
                        # Используем команду /book для бронирования
                        from backend.states import BookingStates
                        await state.set_state(BookingStates.selecting_slot)
                        from backend.handlers.commands import cmd_book
                        await cmd_book(message, state)
                        return
                    elif cmd == "CANCEL_BOOKING":
                        # Используем команду /cancel для отмены
                        from backend.handlers.commands import cmd_cancel
                        await cmd_cancel(message, state)
                        return
                elif rag_answer:
                    await message.answer(rag_answer, reply_markup=keyboard)
                    if parent:
                        await save_dialog(parent.id, "assistant", rag_answer)
                    return
        
        # Запасной вариант
        await message.answer(
            "Это очень интересный вопрос! Я уже передал его нашему главному эксперту, он скоро подключится к диалогу и поможет разобраться.",
            reply_markup=keyboard
        )
        await handle_request_manager_callback(message)

    except Exception as e:
        logging.error(f"CRITICAL ERROR in 'handle_text_message' from {user_id}: {e}", exc_info=True)
        history_for_admin = await load_dialog(user_id)
        await notify_admin_on_error(
            bot=bot, user_id=user_id, username=username,
            error_description=str(e), history=history_for_admin
        )
        await message.answer("Ой, произошла непредвиденная ошибка. Я уже сообщил о ней команде, скоро все починим!")

async def handle_request_manager_callback(event: Union[types.CallbackQuery, types.Message]):
    """Универсальный обработчик запроса менеджера."""
    user = event.from_user
    bot = event.bot
    logging.info(f"[МЕНЕДЖЕР] Пользователь {user.id} запросил помощь менеджера.")
    await notify_admin_of_request(
        bot=bot,
        user=user,
        request_text="Пользователь нажал кнопку «Позвать менеджера»"
    )
    
    text = "Я передал ваш запрос нашему менеджеру. Он скоро с вами свяжется в Telegram! Не переживайте, мы обо всем позаботимся."
    if isinstance(event, types.CallbackQuery):
        await event.message.answer(text)
        await event.answer("Менеджер уже спешит на помощь!")
    else:
        await event.answer(text)

@router.callback_query(F.data == "request_manager")
async def handle_request_manager_button(callback: types.CallbackQuery):
    """Обработчик кнопки 'Позвать менеджера'"""
    await handle_request_manager_callback(callback)
    await callback.answer()

async def start_booking_scenario(message: types.Message, state: FSMContext, user_id: int, username: str):
    """Запускает сценарий бронирования"""
    from backend.handlers.commands import cmd_book
    await cmd_book(message, state)

