import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional
import logging
from backend import config
from backend.utils.retry import sync_retry

logger = logging.getLogger(__name__)


class CalendarService:
    def __init__(self):
        """Инициализация сервиса Google Calendar"""
        if not config.GOOGLE_CALENDAR_ACTIVATE:
            raise ValueError("Google Calendar не активирован в настройках!")
        
        self.calendar_id = config.GOOGLE_CALENDAR_ID
        self.timezone = pytz.timezone(config.TIMEZONE)
        
        # Определяем путь к credentials файлу
        credentials_path = config.GOOGLE_CREDENTIALS_PATH
        
        # Если файл не найден по указанному пути, пробуем найти в корне
        if not os.path.exists(credentials_path):
            # Пробуем найти файл с credentials в корне проекта
            possible_paths = [
                './google-credentials.json',
                './nobugs-478214-0d41160b4771.json',
                './service-account.json'
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    credentials_path = path
                    logger.info(f"Найден файл credentials: {path}")
                    break
            else:
                raise FileNotFoundError(
                    f"Файл credentials не найден. Проверьте путь: {config.GOOGLE_CREDENTIALS_PATH}"
                )
        
        # Загрузка credentials
        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=[
                    'https://www.googleapis.com/auth/calendar',
                    'https://www.googleapis.com/auth/spreadsheets'
                ]
            )
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("Google Calendar API успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Calendar: {e}")
            raise
    
    def get_busy_slots(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Получает занятые слоты из календаря
        
        Args:
            start_time: Начало периода
            end_time: Конец периода
            
        Returns:
            Список словарей с ключами 'start' и 'end' (datetime объекты)
        """
        @sync_retry(
            max_attempts=3,
            initial_delay=1.0,
            max_delay=10.0,
            retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
        )
        def _execute_list():
            return self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
        
        try:
            # Конвертируем в UTC для API
            start_utc = start_time.astimezone(pytz.UTC)
            end_utc = end_time.astimezone(pytz.UTC)
            
            events_result = _execute_list()
            
            events = events_result.get('items', [])
            
            busy_slots = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                if start and end:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    
                    # Конвертируем в локальный часовой пояс
                    start_local = start_dt.astimezone(self.timezone)
                    end_local = end_dt.astimezone(self.timezone)
                    
                    busy_slots.append({
                        'start': start_local,
                        'end': end_local,
                        'summary': event.get('summary', 'Без названия')
                    })
            
            return busy_slots
            
        except Exception as e:
            logger.error(f"Ошибка при получении занятых слотов: {e}", exc_info=True)
            raise
    
    def get_free_slots(
        self, 
        days: int = 1, 
        start_hour: Optional[int] = None, 
        end_hour: Optional[int] = None,
        skip_today: bool = True
    ) -> List[Dict]:
        """
        Получает свободные слоты из календаря
        
        Args:
            days: Количество дней для поиска
            start_hour: Начальный час рабочего дня (по умолчанию из config)
            end_hour: Конечный час рабочего дня (по умолчанию из config)
            skip_today: Пропустить текущий день (начинать со следующего)
            
        Returns:
            Список словарей с информацией о свободных слотах
        """
        start_hour = start_hour or config.START_HOUR
        end_hour = end_hour or config.END_HOUR
        slot_duration = config.SLOT_DURATION
        
        now = datetime.now(self.timezone)
        free_slots = []
        
        # Начинаем со следующего дня, если skip_today=True
        start_offset = 1 if skip_today else 0
        
        for day_offset in range(start_offset, start_offset + days):
            # Начало дня
            current_day = (now + timedelta(days=day_offset)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            
            # Для будущих дней всегда начинаем с начала рабочего дня
            # (не нужно проверять текущее время, так как это уже следующий день)
            
            # Конец дня
            end_of_day = current_day.replace(hour=end_hour, minute=0)
            
            # Получаем занятые слоты для этого дня
            try:
                busy_slots = self.get_busy_slots(current_day, end_of_day)
            except Exception as e:
                logger.error(f"Ошибка при получении занятых слотов для дня {day_offset}: {e}")
                continue
            
            # Генерируем возможные слоты
            current_slot = current_day
            slot_interval = timedelta(minutes=30)  # Проверяем каждые 30 минут
            
            while current_slot < end_of_day:
                slot_end = current_slot + timedelta(minutes=slot_duration)
                
                # Проверяем, не выходит ли за рабочие часы
                if slot_end > end_of_day:
                    break
                
                # Проверяем, не пересекается ли с занятым временем
                is_busy = False
                for busy in busy_slots:
                    if (current_slot < busy['end'] and slot_end > busy['start']):
                        is_busy = True
                        break
                
                if not is_busy:
                    # Форматируем для вывода
                    day_name = self._format_day(current_slot)
                    time_str = self._format_time(current_slot, slot_end)
                    
                    free_slots.append({
                        'start': current_slot,
                        'end': slot_end,
                        'day': day_name,
                        'time': time_str,
                        'datetime_start': current_slot.isoformat(),
                        'datetime_end': slot_end.isoformat()
                    })
                
                current_slot += slot_interval
        
        return free_slots
    
    def create_event(
        self, 
        start_time: datetime, 
        end_time: datetime, 
        summary: str = "Пробное занятие",
        description: str = ""
    ) -> Dict:
        """
        Создает событие в календаре
        
        Args:
            start_time: Начало события
            end_time: Конец события
            summary: Название события
            description: Описание события
            
        Returns:
            Созданное событие
        """
        try:
            # Нужны права на запись
            credentials_path = config.GOOGLE_CREDENTIALS_PATH
            if not os.path.exists(credentials_path):
                possible_paths = [
                    './google-credentials.json',
                    './nobugs-478214-0d41160b4771.json',
                    './service-account.json'
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        credentials_path = path
                        break
            
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            
            # Конвертируем в UTC
            start_utc = start_time.astimezone(pytz.UTC)
            end_utc = end_time.astimezone(pytz.UTC)
            
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_utc.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_utc.isoformat(),
                    'timeZone': 'UTC',
                },
            }
            
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_insert():
                return service.events().insert(
                    calendarId=self.calendar_id,
                    body=event
                ).execute()
            
            created_event = _execute_insert()
            
            logger.info(f"Событие создано: {created_event.get('id')}")
            return created_event
            
        except Exception as e:
            logger.error(f"Ошибка при создании события: {e}", exc_info=True)
            raise
    
    def _format_day(self, dt: datetime) -> str:
        """Форматирует дату для отображения"""
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        
        now = datetime.now(self.timezone)
        if dt.date() == now.date():
            return "Сегодня"
        elif dt.date() == (now + timedelta(days=1)).date():
            return "Завтра"
        else:
            return f"{days[dt.weekday()]}, {dt.day} {months[dt.month - 1]}"
    
    def _format_time(self, start: datetime, end: datetime) -> str:
        """Форматирует время для отображения"""
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    
    def get_user_events(self, user_id: int = None, user_username: str = None, days_ahead: int = 30) -> List[Dict]:
        """
        Получает события пользователя из календаря
        
        Args:
            user_id: Telegram ID пользователя
            user_username: Telegram username пользователя (без @)
            days_ahead: Количество дней вперед для поиска
            
        Returns:
            Список событий пользователя
        """
        try:
            now = datetime.now(self.timezone)
            end_date = now + timedelta(days=days_ahead)
            
            # Конвертируем в UTC
            start_utc = now.astimezone(pytz.UTC)
            end_utc = end_date.astimezone(pytz.UTC)
            
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_list_events():
                return self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=start_utc.isoformat(),
                    timeMax=end_utc.isoformat(),
                    q="Пробное занятие",  # Поиск по названию
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            
            # Получаем все события "Пробное занятие"
            events_result = _execute_list_events()
            
            events = events_result.get('items', [])
            user_events = []
            
            for event in events:
                description = event.get('description', '')
                
                # Проверяем, принадлежит ли событие пользователю
                is_user_event = False
                
                if user_id and f"User ID: {user_id}" in description:
                    is_user_event = True
                elif user_username and f"Telegram: @{user_username}" in description:
                    is_user_event = True
                
                if is_user_event:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    
                    if start and end:
                        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                        
                        # Конвертируем в локальный часовой пояс
                        start_local = start_dt.astimezone(self.timezone)
                        end_local = end_dt.astimezone(self.timezone)
                        
                        user_events.append({
                            'id': event.get('id'),
                            'summary': event.get('summary', 'Пробное занятие'),
                            'description': description,
                            'start': start_local,
                            'end': end_local,
                            'html_link': event.get('htmlLink', ''),
                            'day': self._format_day(start_local),
                            'time': self._format_time(start_local, end_local)
                        })
            
            return user_events
            
        except Exception as e:
            logger.error(f"Ошибка при получении событий пользователя: {e}", exc_info=True)
            raise
    
    def delete_event(self, event_id: str) -> bool:
        """
        Удаляет событие из календаря
        
        Args:
            event_id: ID события для удаления
            
        Returns:
            True если событие успешно удалено, False в случае ошибки
        """
        try:
            # Нужны права на запись
            credentials_path = config.GOOGLE_CREDENTIALS_PATH
            if not os.path.exists(credentials_path):
                possible_paths = [
                    './google-credentials.json',
                    './nobugs-478214-0d41160b4771.json',
                    './service-account.json'
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        credentials_path = path
                        break
            
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            
            # Удаляем событие
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_delete():
                return service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
            
            _execute_delete()
            
            logger.info(f"Событие {event_id} успешно удалено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при удалении события {event_id}: {e}", exc_info=True)
            return False

