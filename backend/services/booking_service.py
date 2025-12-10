from datetime import datetime
from typing import Dict, Optional
import logging
from backend.services.calendar_service import CalendarService
from backend.services.sheets_service import SheetsService
from backend import config

# Импорты для работы с БД
from backend.db.database import (
    get_or_create_parent,
    add_trial_lesson,
    cancel_lesson_db,
    get_lesson_by_id,
    async_session_factory,
    get_children,
    add_child_profile,
)
from backend.db.models import TrialLessonStatus

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(self):
        self.calendar_service = CalendarService()
        self.sheets_service = None
        
        # Инициализируем SheetsService если активирован
        try:
            if config.GOOGLE_SHEETS_ACTIVATE:
                logger.info("Инициализация Google Sheets сервиса...")
                self.sheets_service = SheetsService()
                logger.info("[OK] Google Sheets сервис успешно инициализирован")
            else:
                logger.info("Google Sheets отключен в настройках (GOOGLE_SHEETS_ACTIVATE=False)")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать Google Sheets: {e}", exc_info=True)
            logger.warning("Бронирования будут работать без записи в таблицу")
    
    async def book_slot(
        self, 
        start_time: datetime, 
        end_time: datetime,
        user_name: str = "",
        user_contact: str = "",
        user_phone: str = "",
        user_id: int = None,
        cancel_event_id: str = None,
        child_id: Optional[int] = None,
        course_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """
        Бронирует слот в календаре
        
        Args:
            start_time: Начало слота
            end_time: Конец слота
            user_name: Имя пользователя
            user_contact: Контакт пользователя (Telegram username)
            user_phone: Телефон пользователя (опционально)
            user_id: Telegram ID пользователя
            cancel_event_id: ID события для отмены при переносе (опционально)
            
        Returns:
            Словарь с результатом бронирования
        """
        try:
            cancelled_event = None
            
            # Отменяем конкретную запись, если указан ID (при переносе)
            if cancel_event_id:
                try:
                    if self.calendar_service.delete_event(cancel_event_id):
                        cancelled_event = cancel_event_id
                        logger.info(f"Отменена запись для переноса: {cancel_event_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отменить запись {cancel_event_id}: {e}")
            
            # Проверяем доступность слота
            if not self.is_slot_available(start_time, end_time):
                return {
                    'success': False,
                    'error': 'Слот уже занят'
                }
            
            # Формируем описание
            description_parts = ["Запись на пробное занятие"]
            if user_id:
                description_parts.append(f"User ID: {user_id}")
            if user_name:
                description_parts.append(f"Имя: {user_name}")
            if user_contact:
                description_parts.append(f"Telegram: @{user_contact}")
            if user_phone:
                description_parts.append(f"Телефон: {user_phone}")
            
            description = "\n".join(description_parts)
            
            # Создаем событие
            event = self.calendar_service.create_event(
                start_time=start_time,
                end_time=end_time,
                summary="Пробное занятие",
                description=description
            )
            
            event_id = event.get('id')
            event_link = event.get('htmlLink', '')
            
            # Записываем в Google Sheets если сервис доступен
            # При переносе новая запись создается отдельно, здесь только новые бронирования
            if self.sheets_service and not cancel_event_id:
                logger.info(f"Попытка записи нового бронирования в таблицу для пользователя {user_id}")
                try:
                    success = self.sheets_service.add_booking(
                        start_time=start_time,
                        end_time=end_time,
                        user_name=user_name,
                        user_username=user_contact,
                        user_id=user_id,
                        user_phone=user_phone,
                        event_id=event_id,
                        event_link=event_link,
                        status="Создана"
                    )
                    if success:
                        logger.info(f"[OK] Бронирование успешно записано в таблицу")
                    else:
                        logger.warning(f"[WARN] Не удалось записать бронирование в таблицу")
                except Exception as e:
                    logger.error(f"[ERROR] Ошибка при записи в таблицу: {e}", exc_info=True)
                    # Не прерываем процесс, если запись в таблицу не удалась
            elif not self.sheets_service:
                logger.warning("[WARN] Google Sheets сервис недоступен, запись в таблицу пропущена")
            
            # При переносе создаем новую запись со статусом "Перенесена"
            if self.sheets_service and cancel_event_id:
                try:
                    self.sheets_service.add_booking(
                        start_time=start_time,
                        end_time=end_time,
                        user_name=user_name,
                        user_username=user_contact,
                        user_id=user_id,
                        user_phone=user_phone,
                        event_id=event_id,
                        event_link=event_link,
                        status="Перенесена"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при записи новой записи при переносе: {e}", exc_info=True)
            
            # Сохранение в БД
            lesson_id = None
            if user_id:
                try:
                    # Получаем или создаем родителя
                    parent = await get_or_create_parent(telegram_id=user_id, username=user_contact)
                    
                    if not parent:
                        logging.warning(f"[БД] Не удалось получить/создать родителя для {user_id}. Пропускаем сохранение в БД.")
                        child_id = None
                    # Если child_id не указан, берем первого ребенка или создаем нового
                    elif not child_id:
                        if parent:
                            children = await get_children(parent.id)
                            if children:
                                child_id = children[0].id
                            else:
                                # Создаем ребенка с базовыми данными
                                child = await add_child_profile(
                                    parent_id=parent.id,
                                    name=user_name or "Ребенок",
                                    age=0,  # Возраст неизвестен
                                    interests="",
                                    course_name=course_name,
                                    lessons_count=0
                                )
                                child_id = child.id if child else None
                    
                    # Создаем запись о пробном уроке (только если parent и child_id доступны)
                    if parent and child_id:
                        lesson = await add_trial_lesson(
                            parent_id=parent.id,
                            child_id=child_id,
                            task_id=None,  # task_id не используется в новом проекте
                            event_id=event_id,  # Сохраняем event_id из Google Calendar
                            teacher_id=None,  # teacher_id можно будет добавить позже
                            scheduled_at=start_time,
                            course_name=course_name,
                            notes=notes
                        )
                        lesson_id = lesson.id if lesson else None
                    else:
                        lesson_id = None
                    if lesson_id and parent:
                        logger.info(f"[БД] Пробный урок ID={lesson_id} сохранен в БД для Parent ID={parent.id}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении в БД: {e}", exc_info=True)
                    # Не прерываем процесс, если запись в БД не удалась
                    lesson_id = None
            
            return {
                'success': True,
                'event_id': event_id,
                'html_link': event_link,
                'start': start_time,
                'end': end_time,
                'cancelled_event_id': cancelled_event,
                'lesson_id': lesson_id
            }
            
        except Exception as e:
            logger.error(f"Ошибка при бронировании: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def cancel_booking(self, event_id: str) -> bool:
        """
        Отменяет бронирование и обновляет статус в таблице и БД
        
        Args:
            event_id: ID события для отмены
            
        Returns:
            True если отмена успешна
        """
        try:
            # Удаляем событие из календаря
            success = self.calendar_service.delete_event(event_id)
            
            if not success:
                return False
            
            # Обновляем статус в таблице
            if self.sheets_service:
                try:
                    self.sheets_service.update_booking_status(
                        event_id=event_id,
                        new_status="Отменена",
                        note=""
                    )
                except Exception as e:
                    logger.error(f"Ошибка при обновлении статуса в таблице: {e}", exc_info=True)
                    # Не прерываем процесс, если запись в таблицу не удалась
            
            # Обновляем статус в БД
            try:
                async with async_session_factory() as session:
                    # Ищем урок по event_id
                    from sqlalchemy import select
                    from backend.db.models import TrialLesson
                    
                    stmt = select(TrialLesson).where(TrialLesson.event_id == event_id)
                    result = await session.execute(stmt)
                    lesson = result.scalar_one_or_none()
                    
                    if lesson:
                        await cancel_lesson_db(lesson.id)
                        logger.info(f"[БД] Урок ID={lesson.id} отменен в БД")
                    else:
                        logger.warning(f"[БД] Урок с event_id={event_id} не найден в БД")
            except Exception as e:
                logger.error(f"Ошибка при обновлении статуса в БД: {e}", exc_info=True)
                # Не прерываем процесс, если запись в БД не удалась
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отмене бронирования: {e}", exc_info=True)
            return False
    
    def is_slot_available(self, start_time: datetime, end_time: datetime) -> bool:
        """
        Проверяет доступность слота
        
        Args:
            start_time: Начало слота
            end_time: Конец слота
            
        Returns:
            True если слот свободен, False если занят
        """
        try:
            busy_slots = self.calendar_service.get_busy_slots(start_time, end_time)
            
            for busy in busy_slots:
                if (start_time < busy['end'] and end_time > busy['start']):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности: {e}", exc_info=True)
            return False
    
    async def get_user_lessons_from_db(self, user_id: int) -> list:
        """
        Получает список уроков пользователя из БД
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Список уроков
        """
        try:
            parent = await get_or_create_parent(telegram_id=user_id)
            from backend.db.database import get_full_parent_data
            parent_data = await get_full_parent_data(user_id)
            return parent_data.get('trial_lessons', [])
        except Exception as e:
            logger.error(f"Ошибка при получении уроков из БД: {e}", exc_info=True)
            return []
    
    async def update_lesson_status_in_db(self, lesson_id: int, status: TrialLessonStatus) -> bool:
        """
        Обновляет статус урока в БД
        
        Args:
            lesson_id: ID урока
            status: Новый статус
            
        Returns:
            True если обновление успешно
        """
        try:
            async with async_session_factory() as session:
                from sqlalchemy import update
                from backend.db.models import TrialLesson
                
                stmt = (
                    update(TrialLesson)
                    .where(TrialLesson.id == lesson_id)
                    .values(status=status)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"[БД] Статус урока ID={lesson_id} обновлен на {status}")
                return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса урока в БД: {e}", exc_info=True)
            return False

