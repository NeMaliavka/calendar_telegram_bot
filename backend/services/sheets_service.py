"""
Сервис для работы с Google Sheets API
"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pytz
from backend import config
from backend.utils.retry import sync_retry

logger = logging.getLogger(__name__)


class SheetsService:
    def __init__(self):
        """Инициализация сервиса Google Sheets"""
        if not config.GOOGLE_SHEETS_ACTIVATE:
            raise ValueError("Google Sheets не активирован в настройках!")
        
        self.spreadsheet_id = config.GOOGLE_SHEETS_ID
        self.timezone = pytz.timezone(config.TIMEZONE)
        
        # Загружаем credentials и создаем сервис сначала
        credentials_path = config.GOOGLE_CREDENTIALS_PATH
        
        # Если файл не найден по указанному пути, пробуем найти в корне
        if not os.path.exists(credentials_path):
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
        
        # Загрузка credentials с scope для Sheets
        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/calendar'
                ]
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            
            # Получаем список листов и определяем название
            sheet_name_from_config = config.GOOGLE_SHEETS_NAME
            if sheet_name_from_config:
                # Проверяем, существует ли лист с указанным названием
                try:
                    spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
                    sheet_names = [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
                    logger.info(f"Доступные листы в таблице: {sheet_names}")
                    
                    if sheet_name_from_config in sheet_names:
                        self.sheet_name = sheet_name_from_config
                        logger.info(f"Используется лист: {self.sheet_name}")
                    else:
                        # Используем первый лист, если указанный не найден
                        if sheet_names:
                            self.sheet_name = sheet_names[0]
                            logger.warning(f"Лист '{sheet_name_from_config}' не найден. Используется первый лист: {self.sheet_name}")
                        else:
                            raise ValueError("В таблице нет листов!")
                except Exception as e:
                    logger.error(f"Ошибка при получении списка листов: {e}")
                    # Используем значение из конфига как fallback
                    self.sheet_name = sheet_name_from_config or 'Sheet1'
            else:
                # Если название не указано, используем первый лист
                try:
                    spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
                    sheet_names = [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
                    if sheet_names:
                        self.sheet_name = sheet_names[0]
                        logger.info(f"Название листа не указано, используется первый лист: {self.sheet_name}")
                    else:
                        raise ValueError("В таблице нет листов!")
                except Exception as e:
                    logger.error(f"Ошибка при получении списка листов: {e}")
                    self.sheet_name = 'Sheet1'  # Fallback
            
            logger.info(f"Google Sheets API успешно инициализирован")
            logger.info(f"Spreadsheet ID: {self.spreadsheet_id}")
            logger.info(f"Sheet name: {self.sheet_name}")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Sheets: {e}", exc_info=True)
            raise
        
        # Определяем путь к credentials файлу
        credentials_path = config.GOOGLE_CREDENTIALS_PATH
        
        # Если файл не найден по указанному пути, пробуем найти в корне
        if not os.path.exists(credentials_path):
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
        
        # Загрузка credentials с scope для Sheets
        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/calendar'
                ]
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info(f"Google Sheets API успешно инициализирован")
            logger.info(f"Spreadsheet ID: {self.spreadsheet_id}")
            logger.info(f"Sheet name: {self.sheet_name}")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Sheets: {e}", exc_info=True)
            raise
    
    def _ensure_headers(self):
        """Проверяет наличие заголовков в таблице, создает их если нужно"""
        try:
            logger.debug(f"Проверка заголовков в листе: {self.sheet_name}")
            # Получаем первую строку
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_get():
                return self.service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A1:J1"
                ).execute()
            
            result = _execute_get()
            
            values = result.get('values', [])
            logger.debug(f"Текущие заголовки: {values}")
            
            # Если заголовков нет, создаем их
            if not values or len(values) == 0:
                logger.info("Заголовки отсутствуют, создаю их...")
                headers = [
                    'Дата создания',
                    'Дата и время занятия',
                    'Имя',
                    'Telegram username',
                    'Telegram ID',
                    'Телефон',
                    'Статус',
                    'ID события',
                    'Ссылка на событие',
                    'Примечание'
                ]
                
                body = {
                    'values': [headers]
                }
                
                @sync_retry(
                    max_attempts=3,
                    initial_delay=1.0,
                    max_delay=10.0,
                    retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
                )
                def _execute_update():
                    return self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{self.sheet_name}!A1:J1",
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                
                _execute_update()
                
                logger.info("[OK] Заголовки таблицы созданы")
            else:
                logger.debug("Заголовки уже существуют")
        except HttpError as e:
            logger.error(f"[ERROR] Ошибка при проверке заголовков: {e}")
            logger.error(f"Spreadsheet ID: {self.spreadsheet_id}")
            logger.error(f"Sheet name: {self.sheet_name}")
            logger.error(f"Range: {self.sheet_name}!A1:J1")
            raise
    
    def add_booking(
        self,
        start_time: datetime,
        end_time: datetime,
        user_name: str = "",
        user_username: str = "",
        user_id: Optional[int] = None,
        user_phone: str = "",
        event_id: str = "",
        event_link: str = "",
        status: str = "Создана"
    ) -> bool:
        """
        Добавляет запись о бронировании в таблицу
        
        Args:
            start_time: Начало занятия
            end_time: Конец занятия
            user_name: Имя пользователя
            user_username: Telegram username
            user_id: Telegram ID
            user_phone: Телефон
            event_id: ID события в календаре
            event_link: Ссылка на событие
            status: Статус записи (Создана/Отменена/Перенесена)
            
        Returns:
            True если запись успешно добавлена
        """
        try:
            logger.info(f"Начинаю добавление записи в таблицу: {user_name} - {start_time.strftime('%d.%m.%Y %H:%M')}")
            logger.info(f"Spreadsheet ID: {self.spreadsheet_id}, Sheet: {self.sheet_name}")
            
            # Убеждаемся, что заголовки есть
            try:
                self._ensure_headers()
            except Exception as e:
                logger.error(f"[ERROR] Не удалось проверить/создать заголовки: {e}", exc_info=True)
                return False
            
            # Форматируем даты
            now = datetime.now(self.timezone)
            created_date = now.strftime('%d.%m.%Y %H:%M:%S')
            lesson_date = start_time.strftime('%d.%m.%Y')
            lesson_time = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
            lesson_datetime = f"{lesson_date} {lesson_time}"
            
            # Подготавливаем строку данных
            row = [
                created_date,                    # Дата создания
                lesson_datetime,                 # Дата и время занятия
                user_name or '',                 # Имя
                f"@{user_username}" if user_username else '',  # Telegram username
                str(user_id) if user_id else '', # Telegram ID
                user_phone or '',                # Телефон
                status,                          # Статус
                event_id or '',                  # ID события
                event_link or '',                # Ссылка на событие
                ''                               # Примечание
            ]
            
            # Добавляем строку в конец таблицы
            body = {
                'values': [row]
            }
            
            logger.info(f"Добавляю строку в таблицу: {self.sheet_name}!A:J")
            logger.debug(f"Данные строки: {row}")
            
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_append():
                return self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A:J",
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
            
            result = _execute_append()
            
            updated_cells = result.get('updates', {}).get('updatedCells', 0)
            logger.info(f"[OK] Запись успешно добавлена в таблицу: {user_name} - {lesson_datetime} (обновлено ячеек: {updated_cells})")
            return True
            
        except HttpError as e:
            logger.error(f"[ERROR] HTTP ошибка при добавлении записи в таблицу: {e}")
            logger.error(f"Детали ошибки: {e.error_details if hasattr(e, 'error_details') else 'Нет деталей'}")
            logger.error(f"Spreadsheet ID: {self.spreadsheet_id}, Sheet: {self.sheet_name}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Неожиданная ошибка при работе с таблицей: {e}", exc_info=True)
            return False
    
    def update_booking_status(
        self,
        event_id: str,
        new_status: str,
        note: str = ""
    ) -> bool:
        """
        Обновляет статус записи в таблице по ID события
        
        Args:
            event_id: ID события в календаре
            new_status: Новый статус (Отменена/Перенесена)
            note: Примечание (например, новое время при переносе)
            
        Returns:
            True если статус успешно обновлен
        """
        try:
            # Получаем все данные из таблицы
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_get_all():
                return self.service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A:J"
                ).execute()
            
            result = _execute_get_all()
            
            values = result.get('values', [])
            
            if len(values) < 2:  # Только заголовки
                logger.warning("Таблица пуста, нечего обновлять")
                return False
            
            # Ищем строку с нужным event_id (колонка H, индекс 7)
            found_row = None
            row_index = None
            
            for i, row in enumerate(values[1:], start=2):  # Пропускаем заголовки
                if len(row) > 7 and row[7] == event_id:  # Колонка H (индекс 7)
                    found_row = row
                    row_index = i
                    break
            
            if not found_row:
                logger.warning(f"Запись с event_id {event_id} не найдена в таблице")
                return False
            
            # Обновляем статус и примечание
            now = datetime.now(self.timezone)
            note_with_date = f"{new_status} {now.strftime('%d.%m.%Y %H:%M')}"
            if note:
                note_with_date += f" | {note}"
            
            # Обновляем колонки: Статус (G, индекс 6) и Примечание (J, индекс 9)
            # Дополняем строку до нужной длины если нужно
            while len(found_row) < 10:
                found_row.append('')
            
            found_row[6] = new_status  # Статус
            found_row[9] = note_with_date  # Примечание
            
            # Обновляем строку
            body = {
                'values': [found_row]
            }
            
            @sync_retry(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=[HttpError, ConnectionError, TimeoutError, Exception]
            )
            def _execute_update_status():
                return self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A{row_index}:J{row_index}",
                    valueInputOption='RAW',
                    body=body
                ).execute()
            
            result = _execute_update_status()
            
            logger.info(f"Статус записи {event_id} обновлен на: {new_status}")
            return True
            
        except HttpError as e:
            logger.error(f"Ошибка при обновлении статуса в таблице: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обновлении таблицы: {e}", exc_info=True)
            return False

