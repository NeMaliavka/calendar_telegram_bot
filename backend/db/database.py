# backend/db/database.py
"""
Модуль для асинхронной работы с базой данных.
Содержит функции для создания, чтения, обновления и удаления
основных сущностей: Parent, Child, TrialLesson и др.
"""

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, not_, update, delete, func, desc
from decimal import Decimal
from typing import List, Dict, Optional, Any

from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from .models import (
    Base, Parent, Child, DialogHistory, TrialLesson,
    TrialLessonStatus, Payment, PaymentStatus, Feedback, WaitlistEntry, OnboardingStep,
    Teacher, Group  
)

from backend import config

# --- Инициализация (ленивая) ---
DATABASE_URL = config.DATABASE_URL
async_engine = None
async_session_factory = None

def _get_engine():
    """Ленивая инициализация engine. Создается только при первом использовании."""
    global async_engine, async_session_factory
    
    if async_engine is None:
        if not DATABASE_URL:
            return None
        
        async_engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,          # Количество постоянных соединений в пуле
            max_overflow=10,      # Доп. соединения сверх основного пула
            pool_timeout=30,      # Время ожидания свободного соединения
            pool_recycle=1800,    # Переподключение каждые 30 минут (важно для облака)
            pool_pre_ping=True    # Проверка соединения перед использованием
        )
        async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        logging.info(f"Database engine initialized with URL: {DATABASE_URL[:20]}...")
    
    return async_engine

def _get_session_factory():
    """Получить session factory, инициализируя engine если нужно."""
    if not DATABASE_URL:
        return None
    if async_session_factory is None:
        _get_engine()
    return async_session_factory

async def init_db():
    """Инициализирует БД: создаёт все таблицы по моделям."""
    if not DATABASE_URL:
        logging.warning("[БД] DATABASE_URL не установлен. Пропускаем инициализацию БД.")
        return
    
    try:
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logging.info("[БД] База данных и все таблицы успешно проверены/созданы.")
    except SQLAlchemyError as e:
        logging.critical(f"[БД] КРИТИЧЕСКАЯ ОШИБКА при инициализации: {e}", exc_info=True)
        raise

# --- Вспомогательные функции работы с временем ---
def to_utc_naive(dt: datetime) -> datetime:
    """Переводит время из московской зоны в UTC-наивное."""
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            # Здесь предполагаем, что dt уже в UTC-naive, никаких преобразований не делаем
            return dt
        else:
            # Если время с tzinfo, переводим в московское, а потом в UTC без tzinfo
            dt_moscow = dt.astimezone(ZoneInfo("Europe/Moscow"))
            dt_utc = dt_moscow.astimezone(timezone.utc)
            return dt_utc.replace(tzinfo=None)
    except Exception as e:
        logging.error(f"[DB] Ошибка конвертации Moscow->UTC-naive: {e}")
        return dt

def utc_naive_to_moscow(dt: datetime) -> datetime:
    """Переводит UTC-наивное время из БД в московское."""
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            # Наивное время считаем, что оно в UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Europe/Moscow"))
    except Exception as e:
        logging.error(f"[DB] Ошибка конвертации UTC-naive в Москву: {e}")
        return dt

async def increment_irrelevant_count(user_id: int, username: Optional[str]) -> int:
    """
    Увеличивает счетчик нерелевантных сообщений для пользователя.
    Если DATABASE_URL не установлен, возвращает 0.
    Если пользователя нет в БД, создает для него запись и устанавливает счетчик в 1.
    """
    if not DATABASE_URL:
        logging.warning(f"[БД] DATABASE_URL не установлен. Пропускаем increment_irrelevant_count для {user_id}.")
        return 0
    
    # Открываем сессию для работы с БД
    session_factory = _get_session_factory()
    if session_factory is None:
        return 0
    
    async with session_factory() as session:
        # Шаг 1: Ищем пользователя по его telegram_id
        stmt = select(Parent).where(Parent.telegram_id == user_id)
        result = await session.execute(stmt)
        parent = result.scalar_one_or_none()

        if parent:
            # Шаг 2а: Если пользователь НАЙДЕН, просто увеличиваем его счетчик
            parent.irrelevant_count += 1
            new_count = parent.irrelevant_count
            logging.info(f"Счетчик нерелевантных сообщений для Parent ID={parent.id} увеличен до {new_count}.")
        else:
            # Шаг 2б: Если пользователь НЕ НАЙДЕН, создаем новую запись
            logging.info(f"Пользователь с telegram_id={user_id} не найден. Создаем новую запись в БД.")
            parent = Parent(
                telegram_id=user_id,
                username=username,
                irrelevant_count=1, 
                is_blocked=False,
                is_enrolled=False,
                onboarding_step=OnboardingStep.NOT_STARTED,
                user_data={}
            )
            
            session.add(parent)
            new_count = 1

        # Шаг 3: Сохраняем все изменения (обновление или создание) в базе данных
        await session.commit()
        
        return parent.irrelevant_count # Возвращаем актуальное значение счетчика

# --- Parent (Пользователь) ---

async def get_or_create_parent(telegram_id: int, username: Optional[str] = None) -> Optional[Parent]:
    """
    Находит родителя по telegram_id или создает нового.
    Ключевое исправление: теперь функция всегда работает с telegram_id.
    Если DATABASE_URL не установлен, возвращает None.
    """
    if not DATABASE_URL:
        logging.warning(f"[БД] DATABASE_URL не установлен. Пропускаем get_or_create_parent для {telegram_id}.")
        return None
    
    session_factory = _get_session_factory()
    if session_factory is None:
        return None
    
    async with session_factory() as session:
        stmt = select(Parent).where(Parent.telegram_id == telegram_id)
        result = await session.execute(stmt)
        parent = result.scalar_one_or_none()

        if parent:
            logging.info(f"[БД] Найден существующий Parent ID={parent.id} для telegram_id={telegram_id}")
            return parent
        else:
            new_parent = Parent(telegram_id=telegram_id, username=username)
            session.add(new_parent)
            await session.commit()
            await session.refresh(new_parent)
            logging.info(f"[БД] Новый Parent ID={new_parent.id} успешно создан для telegram_id={telegram_id}")
            return new_parent

async def get_parent_by_id(session: AsyncSession, parent_id: int) -> Optional[Parent]:
    """
    Находит родителя по его первичному ключу (ID).
    Это самый быстрый способ получить объект, если известен его ID.
    """
    parent = await session.get(Parent, parent_id)
    if not parent:
        logging.warning(f"[БД] Parent с ID={parent_id} не найден.")
    return parent

async def save_parent_answers(parent_id: int, data: dict) -> None:
    """Сохраняет или обновляет анкетные данные родителя в поле user_data."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Parent).where(Parent.id == parent_id).values(user_data=data)
        )
        await session.commit()

async def block_user(parent_id: int) -> None:
    """
    Блокирует пользователя, устанавливая флаг is_blocked = True.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Parent).where(Parent.id == parent_id).values(is_blocked=True)
        )
        await session.commit()
        logging.error(f"[МОДЕРАЦИЯ] Пользователь Parent ID={parent_id} был заблокирован из-за превышения лимита нерелевантных сообщений.")

# --- Onboarding (Анкетирование) ---

async def set_onboarding_step(telegram_id: int, step: str):
    """Обновляет текущий шаг онбординга у родителя."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        stmt = update(Parent).where(Parent.telegram_id == telegram_id).values(onboarding_step=step)
        await session.execute(stmt)
        await session.commit()
        logging.info(f"[БД] Для Parent с telegram_id={telegram_id} шаг онбординга установлен на '{step}'")

# --- Child (Ребенок) ---

async def add_child_profile(parent_id: int, name: str, age: int, interests: Optional[str] = None,
                            course_name: Optional[str] = None, lessons_count: Optional[int] = None) -> Child:
    """Создаёт профиль ребёнка и привязывает его к родителю."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        child = Child(
            parent_id=parent_id, name=name, age=age, interests=interests,
            course_name=course_name, lessons_count=lessons_count
        )
        session.add(child)
        await session.commit()
        await session.refresh(child)
        logging.info(f"[БД] Ребенок '{name}' (ID={child.id}) добавлен для Parent ID={parent_id}")
        return child

async def get_children(parent_id: int) -> List[Child]:
    """Возвращает список всех детей для указанного родителя."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Child).where(Child.parent_id == parent_id))
        return list(result.scalars().all())

# --- DialogHistory (История диалога) ---

async def save_dialog(parent_id: int, role: str, message: str, fsm_state: Optional[str] = None, intent: Optional[str] = None):
    """Сохраняет одно сообщение (от пользователя или бота) в историю диалога. Если DATABASE_URL не установлен, просто пропускает."""
    if not DATABASE_URL:
        return
    from sqlalchemy.exc import IntegrityError
    session_factory = _get_session_factory()
    if session_factory is None:
        return
    async with session_factory() as session:
        entry = DialogHistory(parent_id=parent_id, role=role, message=message, fsm_state=fsm_state, intent=intent)
        session.add(entry)
        try:
            await session.commit()
        except IntegrityError as e:
            # Если есть проблема с sequences, можно добавить обработку позже
            logging.error(f"[БД] Ошибка при сохранении диалога: {e}")
            raise

async def load_dialog(parent_id: int, limit: int = 20) -> List[Dict[str, str]]:
    """Загружает последние сообщения из диалога для контекста LLM. Если DATABASE_URL не установлен, возвращает пустой список."""
    if not DATABASE_URL:
        return []
    session_factory = _get_session_factory()
    if session_factory is None:
        return []
    async with session_factory() as session:
        result = await session.execute(
            select(DialogHistory).where(DialogHistory.parent_id == parent_id)
            .order_by(desc(DialogHistory.created_at)).limit(limit)
        )
        entries = result.scalars().all()
        return [{"role": e.role, "content": e.message} for e in reversed(entries)]

# --- TrialLesson (Пробный урок) ---

async def add_trial_lesson(parent_id: int, child_id: int, task_id: Optional[int], event_id: Optional[int],
                           teacher_id: Optional[int], scheduled_at: datetime, course_name: Optional[str] = None,
                           notes: Optional[str] = None) -> TrialLesson:
    """Создаёт запись о новом пробном уроке в базе данных, сохраняя время в UTC."""
    scheduled_at_naive_utc = to_utc_naive(scheduled_at)

    session_factory = _get_session_factory()
    async with session_factory() as session:
        lesson = TrialLesson(
            parent_id=parent_id, 
            child_id=child_id, 
            task_id=task_id, 
            event_id=event_id,
            teacher_id=teacher_id, 
            scheduled_at=scheduled_at_naive_utc, 
            status=TrialLessonStatus.PLANNED,
            course_name=course_name, 
            notes=notes
        )
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
        logging.info(f"[БД] Пробный урок ID={lesson.id} добавлен для Parent ID={parent_id}, Child ID={child_id}")
        return lesson

async def update_trial_time(session: AsyncSession, lesson_id: int, new_time: datetime):
    """Обновляет время запланированного пробного урока."""
    try:
        stmt = (
            update(TrialLesson)
            .where(TrialLesson.id == lesson_id)
            .values(scheduled_at=new_time)
        )
        await session.execute(stmt)
        await session.commit()
        logging.info(f"Время для урока ID={lesson_id} успешно обновлено на {new_time}.")
        return True
    except Exception as e:
        logging.error(f"Не удалось обновить время для урока ID={lesson_id}: {e}", exc_info=True)
        await session.rollback() # Откатываем изменения в случае ошибки
        return False

async def cancel_lesson_db(lesson_id: int):
    """Устанавливает статус пробного урока на 'CANCELLED'."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(TrialLesson).where(TrialLesson.id == lesson_id).values(status=TrialLessonStatus.CANCELLED)
        )
        await session.commit()
        logging.info(f"[БД] TrialLesson ID={lesson_id} был отменен.")

# --- Полный профиль ---

async def get_full_parent_data(user_id: int, username: Optional[str] = None):
    """
    Получает полный профиль родителя со всеми связанными данными:
    детьми, пробными уроками и платежами, включая анкетные данные из user_data.
    Если DATABASE_URL не установлен, возвращает None.
    """
    if not DATABASE_URL:
        logging.warning(f"[БД] DATABASE_URL не установлен. Пропускаем get_full_parent_data для {user_id}.")
        return None
    
    session_factory = _get_session_factory()
    if session_factory is None:
        return None
    
    async with session_factory() as session:
        # --- ШАГ 1: ИЩЕМ ИЛИ СОЗДАЕМ ПОЛЬЗОВАТЕЛЯ ---
        stmt = (
            select(Parent)
            .where(Parent.telegram_id == user_id)
            .options(
                selectinload(Parent.children),
                selectinload(Parent.trial_lessons),
                selectinload(Parent.payments)
            )
        )
        result = await session.execute(stmt)
        parent = result.scalar_one_or_none()

        if not parent:
            logging.warning(f"[БД] Родитель с telegram_id={user_id} не найден. Создаем новый.")
            parent = Parent(telegram_id=user_id, username=username)
            session.add(parent)
            await session.commit()

            user_profile_data = parent.user_data or {}

            children_data = []
            trial_lessons_data = []
            payments_data = []

            parent_dict_for_new_user = {
                "id": parent.id,
                "telegram_id": parent.telegram_id,
                "username": parent.username,
                "is_blocked": parent.is_blocked,
                "irrelevant_count": parent.irrelevant_count,
                "onboarding_completed_at": parent.onboarding_completed_at.isoformat() if parent.onboarding_completed_at else None,
                "user_data": user_profile_data,
                "children": children_data,
                "trial_lessons": trial_lessons_data,
                "payments": payments_data,
                "full_name": parent.full_name,
                "phone": parent.phone,
                "email": parent.email,
                "parent_name_from_user_data": user_profile_data.get("parent_name"),
                "parent_phone_from_user_data": user_profile_data.get("parent_phone"),
                "parent_email_from_user_data": user_profile_data.get("parent_email"),
                "parent_contact_tg": user_profile_data.get("parent_contact_tg")
            }
            return parent_dict_for_new_user

        # --- ШАГ 2: СОБИРАЕМ СЛОВАРЬ ВНУТРИ СЕССИИ ДЛЯ СУЩЕСТВУЮЩЕГО РОДИТЕЛЯ ---
        user_profile_data = parent.user_data or {}

        children_data = [
            {"id": child.id, "name": child.name, "age": child.age, "interests": child.interests}
            for child in parent.children
        ]

        # Дополнительно, если детей нет в children, но есть данные в user_data, можно добавить их
        if not children_data and user_profile_data.get("child_name"):
            children_data.append({
                "id": None,
                "name": user_profile_data.get("child_name"),
                "age": user_profile_data.get("child_age"),
                "interests": user_profile_data.get("child_interests")
            })

        trial_lessons_data = []
        for lesson in parent.trial_lessons:
            trial_lessons_data.append({
                "id": lesson.id,
                "child_id": lesson.child_id,
                "teacher_id": lesson.teacher_id,
                "scheduled_at": lesson.scheduled_at.isoformat() if lesson.scheduled_at else None,
                "status": lesson.status.name if lesson.status else None,
                "task_id": lesson.task_id,
                "event_id": lesson.event_id
            })
        payments_data = [
            {"id": payment.id, "amount": float(payment.amount), "status": payment.status.name}
            for payment in parent.payments
        ]

        parent_data = {
            "id": parent.id,
            "telegram_id": parent.telegram_id,
            "username": parent.username,
            "is_blocked": parent.is_blocked,
            "irrelevant_count": parent.irrelevant_count,
            "onboarding_completed_at": parent.onboarding_completed_at.isoformat() if parent.onboarding_completed_at else None,
            "user_data": user_profile_data,
            "children": children_data,
            "trial_lessons": trial_lessons_data,
            "payments": payments_data,
            "full_name": parent.full_name,
            "phone": parent.phone,
            "email": parent.email,
            "parent_name_from_user_data": user_profile_data.get("parent_name"),
            "parent_phone_from_user_data": user_profile_data.get("parent_phone"),
            "parent_email_from_user_data": user_profile_data.get("parent_email"),
            "parent_contact_tg": user_profile_data.get("parent_contact_tg")
        }
        logging.info(f"[БД] Полный профиль для Parent ID={parent.id} успешно сформирован.")
        
        return parent_data

async def unblock_and_reset(telegram_id: int) -> None:
    """
    Снимает блокировку с родителя и сбрасывает его счетчик
    нерелевантных сообщений до нуля.
    """
    logging.info(f"[МОДЕРАЦИЯ] Попытка разблокировать Parent ID= {int(telegram_id)}")
    session_factory = _get_session_factory()
    async with session_factory() as session:
        stmt = (
            update(Parent)
            .where(Parent.telegram_id == telegram_id)
            .values(is_blocked=False, irrelevant_count=0)
        )
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount > 0:
            logging.info(f"[МОДЕРАЦИЯ] Пользователь с telegram_id={telegram_id} успешно разблокирован.")
            return True
        else:
            logging.warning(f"[МОДЕРАЦИЯ] Не удалось найти пользователя с telegram_id={telegram_id} для разблокировки.")
            return False
        
async def count_enrolled() -> int:
    """
    Подсчитывает общее количество зачисленных на курс родителей.
    Зачисленными считаются те, у кого флаг is_enrolled=True.
    """
    logging.info("[DB] Выполняется подсчет зачисленных студентов...")
    session_factory = _get_session_factory()
    async with session_factory() as session:
        stmt = select(func.count(Parent.id)).where(Parent.is_enrolled == True)
        result = await session.execute(stmt)
        enrolled_count = result.scalar_one_or_none() or 0
        logging.info(f"[DB] Найдено {enrolled_count} зачисленных студентов.")
        return enrolled_count

async def add_waitlist_entry(parent_id: int, contact: str, age_group: str, deal_id: Optional[int] = None) -> WaitlistEntry:
    """
    Добавляет родителя в лист ожидания и сохраняет запись в БД.
    """
    logging.info(f"[БАЗА ДАННЫХ] Добавление Parent ID={parent_id} в лист ожидания для группы '{age_group}'.")
    session_factory = _get_session_factory()
    async with session_factory() as session:
        new_entry = WaitlistEntry(
            parent_id=parent_id,
            contact=contact,
            age_group=age_group,
            deal_id=deal_id,
        )
        session.add(new_entry)
        await session.commit()
        await session.refresh(new_entry)
        logging.info(f"[БАЗА ДАННЫХ] Запись в лист ожидания ID={new_entry.id} успешно создана.")
        return new_entry

async def complete_onboarding_in_db(
        parent_id: int,
        full_name: Optional[str],
        phone: Optional[str],
        email: Optional[str],
        user_data: dict
    ) -> None:
    """
    Атомарно завершает онбординг: обновляет статус, время завершения и анкетные данные.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        dt_aware = datetime.now(timezone.utc)
        dt_naive = dt_aware.replace(tzinfo=None)
        stmt = (
            update(Parent)
            .where(Parent.id == parent_id)
            .values(
                onboarding_completed_at=dt_naive,
                user_data=user_data,
                onboarding_step=OnboardingStep.COMPLETED,
                full_name=full_name,
                phone=phone,
                email=email
            )
        )
        await session.execute(stmt)
        await session.commit()
        logging.info(f"[БД] Онбординг для Parent ID={parent_id} полностью завершен в базе данных.")

async def get_lesson_by_id(session: AsyncSession, lesson_id: int):
    """Получает урок по его ID из базы данных."""
    try:
        stmt = select(TrialLesson).options(
            selectinload(TrialLesson.parent),
            selectinload(TrialLesson.child)
        ).where(TrialLesson.id == lesson_id)
        result = await session.execute(stmt)
        lesson = result.scalar_one_or_none()
        if not lesson:
            logging.warning(f"Урок с ID {lesson_id} не найден в БД.")
        return lesson
    except Exception as e:
        logging.error(f"Ошибка при получении урока по ID {lesson_id}: {e}", exc_info=True)
        return None
    
async def get_child_name(child_id: int) -> Optional[str]:
    """
    Возвращает имя ребёнка по его ID.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Child.name).where(Child.id == child_id)
        )
        name = result.scalar_one_or_none()
        if not name:
            logging.warning(f"[БД] Ребенок с ID={child_id} не найден.")
        return name

async def is_time_slot_busy(
    session: AsyncSession,
    new_time: datetime,
    child_id: Optional[int] = None,
    ignore_lesson_id: Optional[int] = None
) -> bool:
    """
    Проверяет, занят ли указанный слот времени (new_time), например, для переноса/бронирования.
    Можно опционально игнорировать указанный урок (при переносе).
    Можно проверять по child_id или другой логике.
    """
    conditions = [
        (TrialLesson.scheduled_at == new_time),
        (TrialLesson.status == TrialLessonStatus.PLANNED)
    ]
    if child_id is not None:
        conditions.append(TrialLesson.child_id == child_id)
    if ignore_lesson_id is not None:
        conditions.append(TrialLesson.id != ignore_lesson_id)

    stmt = select(TrialLesson.id).where(and_(*conditions))
    result = await session.execute(stmt)
    busy = result.scalar_one_or_none() is not None
    return busy

async def assign_child_to_teacher(
    child_id: int, 
    teacher_id: int,
    group_name: Optional[str] = None
) -> bool:
    """
    Привязывает ребенка к учителю, опционально создавая или используя группу с именем group_name.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        child = await session.get(Child, child_id)
        if child is None:
            logging.warning(f"[БД] Ребенок с id={child_id} не найден в базе учителей.")
            return False

        teacher = await session.get(Teacher, teacher_id)
        if teacher is None:
            logging.warning(f"[БД] Учитель с id={teacher_id} не найден.")
            return False

        group = None
        if group_name:
            stmt = select(Group).where(
                Group.teacher_id == teacher_id,
                Group.name == group_name
            )
            result = await session.execute(stmt)
            group = result.scalar_one_or_none()

        if group is None:
            group = Group(
                name=group_name or f"Группа учителя {teacher_id}",
                teacher_id=teacher_id,
                children=[]
            )
            session.add(group)
            await session.flush()

        if child not in group.children:
            group.children.append(child)
            logging.info(f"[БД] Ребенок id={child_id} добавлен в группу '{group.name}' учителя id={teacher_id}.")
        else:
            logging.info(f"[БД] Ребенок id={child_id} уже в группе '{group.name}' учителя id={teacher_id}.")

        await session.commit()
        return True

async def get_teacher_and_group_for_child(child_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает информацию о педагоге и группе, к которой принадлежит ребенок,
    или None, если не найден ребенок или привязки.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(Group, Teacher)
            .join(Group.teacher)
            .join(Group.children)           
            .where(Child.id == child_id)
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            logging.warning(f"[БД] Нет группы и учителя для ребенка id={child_id}.")
            return None

        group, teacher = row
        return {
            "group_id": group.id,
            "group_name": group.name,
            "teacher_id": teacher.id,
            "teacher_first_name": teacher.first_name,
            "teacher_last_name": teacher.last_name,
            "teacher_phone": teacher.phone,
            "teacher_telegram": teacher.telegram,
        }
    
async def mark_lesson_completed(session: AsyncSession, lesson_id: int) -> Optional[TrialLesson]:
    """
    Отмечает пробный урок с lesson_id как завершённый (например, ставит статус COMPLETED).
    Возвращает обновлённый объект урока.
    """
    try:
        stmt = (
            update(TrialLesson)
            .where(TrialLesson.id == lesson_id)
            .values(status=TrialLessonStatus.COMPLETED)
            .returning(TrialLesson)
        )
        result = await session.execute(stmt)
        await session.commit()
        updated_lesson = result.scalar_one_or_none()
        if updated_lesson:
            logging.info(f"Урок ID={lesson_id} отметили как завершённый.")
        else:
            logging.warning(f"Урок ID={lesson_id} не найден при попытке отметить завершённым.")
        return updated_lesson
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса урока ID={lesson_id}: {e}", exc_info=True)
        await session.rollback()
        return None

async def get_lessons_to_check(check_time: datetime) -> list:
    """
    Возвращает список уроков, начавшихся в время `check_time` (±1 минута) и ещё не отмеченных как COMPLETED/CANCELLED.
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        if check_time.tzinfo is not None:
            check_time = check_time.replace(tzinfo=None)

        time_from = check_time - timedelta(minutes=1)
        time_to = check_time + timedelta(minutes=1)
        stmt = select(TrialLesson).where(
            and_(
                TrialLesson.scheduled_at >= time_from,
                TrialLesson.scheduled_at <= time_to,
                TrialLesson.status == TrialLessonStatus.PLANNED,
            )
        )
        result = await session.execute(stmt)
        lessons = result.scalars().all()
        return lessons
    
async def mark_lesson_reminder_sent(session: AsyncSession, lesson_id: int):
    """Отмечает отправку напоминания для урока."""
    await session.execute(
        update(TrialLesson)
        .where(TrialLesson.id == lesson_id)
        .values(notified_new=True)
    )
    await session.commit()

async def db_ping():
    """Проверка подключения к БД."""
    if not DATABASE_URL:
        logging.warning("[БД] DATABASE_URL не установлен. Пропускаем проверку подключения.")
        return
    
    try:
        session_factory = _get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(func.now()))
            logging.info(f"Postgres time: {result.scalar_one()}")
    except Exception as e:
        logging.error(f"[БД] Ошибка при проверке подключения: {e}")
        raise

