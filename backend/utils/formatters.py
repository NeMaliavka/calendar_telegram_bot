# backend/utils/formatters.py

import logging
import re
from typing import Optional
from dateutil import parser 
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# Словарь для склонения названий месяцев в родительном падеже
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}
WEEKDAYS_RU = {
    0: ("Понедельник", "Пн"), 
    1: ("Вторник", "Вт"), 
    2: ("Среда", "Ср"),
    3: ("Четверг", "Чт"), 
    4: ("Пятница", "Пт"), 
    5: ("Суббота", "Сб"),
    6: ("Воскресенье", "Вс")
}

try:
    from backend.utils.text_tools import inflect_name
    MORPHOLOGY_ENABLED = True
except ImportError:
    logging.warning("Утилиты морфологии (text_tools.py) не найдены.")
    MORPHOLOGY_ENABLED = False
    def inflect_name(name: str, _: str) -> str: return name

MOSCOW_TZ = timezone(timedelta(hours=3))

def parse_datetime_iso(dt_str: str) -> Optional[datetime]:
    """
    Безопасно преобразует строку ISO в datetime.
    Если таймзона не указана — СЧИТАЕТСЯ, ЧТО ЭТО UTC.
    """
    if not dt_str:
        return None
    try:
        dt = parser.isoparse(dt_str)
        # Если дата "наивная" (без таймзоны), мы считаем ее временем в UTC.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logging.error(f"Не удалось распарсить дату-время из строки: {dt_str}")
        return None

#---- ИСПРАВЛЕНИЕ 14.08.2025: парсер для даты формата ISO и dd.mm.yyyy HH:MM:SS-----#
def parse_any_date(date_str: str):
    """Пробуем ISO, потом dd.mm.yyyy HH:MM:SS."""
    try:
        return parser.isoparse(date_str)
    except ValueError:
        try:
            return datetime.strptime(date_str, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            except ValueError:
                raise  # если вообще не распарсилось

def parse_datetime_from_string(dt_string: str) -> datetime:
    """
    Парсит datetime из строки ISO формата.
    Совместимость с backend/utils.py
    
    Args:
        dt_string: Строка в формате ISO
        
    Returns:
        Объект datetime (с таймзоной если указана, иначе UTC)
    """
    if not dt_string:
        raise ValueError("Пустая строка для парсинга datetime")
    
    try:
        # Пробуем ISO формат
        dt = parser.isoparse(dt_string)
        # Если дата "наивная" (без таймзоны), считаем ее UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Если ISO не сработал, пробуем другие форматы
        try:
            dt = datetime.strptime(dt_string, "%d.%m.%Y %H:%M:%S")
            return dt.replace(tzinfo=ZoneInfo("Europe/Moscow"))
        except ValueError:
            try:
                dt = datetime.strptime(dt_string, "%d.%m.%Y %H:%M")
                return dt.replace(tzinfo=ZoneInfo("Europe/Moscow"))
            except ValueError:
                raise ValueError(f"Не удалось распарсить дату: {dt_string}")

def format_response_with_inflection(template: str, data: dict) -> str:
    """
    Надежно форматирует строку: сначала склоняет имена, а затем подставляет остальные данные.
    Ищет плейсхолдеры вида {child_name:datv} и простые {parent_name}.
    """
    if not template: return ""
    # Внутренняя функция, которая будет заменять плейсхолдеры со склонением
    def _replace_inflected(match):
        var_name, case = match.group(1), match.group(2)
        original_value = data.get(var_name, "")
        
        # Если морфология включена - склоняем
        if MORPHOLOGY_ENABLED:
            return inflect_name(str(original_value), case)
        # Если морфология отключена - просто возвращаем исходное значение
        else:
            return str(original_value)
    processed_template = re.sub(r'\{(\w+):(\w+)\}', _replace_inflected, template)
    
    try:
        # Используем стандартный .format() с исходными данными
        return processed_template.format(**data)
    except KeyError as e:
        logging.warning(f"В шаблоне не хватило данных для ключа: {e}. Шаблон: '{processed_template}'")
        # Возвращаем частично отформатированный шаблон, чтобы не падать с ошибкой
        return processed_template

def format_date_russian(dt: datetime, mode: str = 'full') -> str:
    """
    Форматирует объект datetime в красивую русскую строку.

    Args:
        dt (datetime): Объект даты и времени.
        mode (str): Режим форматирования:
                    'full' -> "17 июля (Четверг) в 17:00"
                    'short' -> "17 июля в 17:00"
                    'short_with_weekday' -> "17 июля, Чт" (без времени)

    Returns:
        str: Отформатированная строка.
    """
    if not isinstance(dt, datetime):
        logging.error(f"В format_date_russian передан неверный тип: {type(dt)}")
        return "Некорректная дата"

    day = dt.day
    month = MONTHS_RU.get(dt.month, "")
    weekday_full, weekday_short = WEEKDAYS_RU.get(dt.weekday(), ("?", "?"))

    time_str = dt.strftime('%H:%M')

    if mode == 'full':
        return f"{day} {month} ({weekday_full}) в {time_str}"
    
    elif mode == 'short':
        return f"{day} {month} в {time_str}"
    
    elif mode == 'short_with_weekday':
        # Этот формат вернет "17 июля, Чт", гарантированно без времени.
        return f"{day} {month}, {weekday_short}"
    
    return dt.strftime('%d.%m.%Y')

def get_moscow_time_from_db(dt_iso_str: str) -> Optional[datetime]:
    """
    Принимает ISO-строку времени из БД (предполагается, что она в UTC и aware)
    и возвращает datetime-объект в московском часовом поясе.
    """
    dt_utc = parse_datetime_iso(dt_iso_str)
    if not dt_utc:
        return None
    
    # Убеждаемся, что dt_utc действительно aware и в UTC
    if dt_utc.tzinfo is None:
        logging.warning(f"Найдена наивная дата в БД: {dt_iso_str}. Предполагаем UTC.")
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    elif dt_utc.tzinfo != timezone.utc:
        # Если вдруг из БД пришла дата с другим aware-таймзоной, конвертируем её в UTC
        dt_utc = dt_utc.astimezone(timezone.utc)

    moscow_tz = ZoneInfo("Europe/Moscow")
    return dt_utc.astimezone(moscow_tz)

def get_user_data_summary(user_data: dict, for_bitrix: bool = False) -> str:
    """
    Формирует красивую сводку по анкете пользователя для отправки в Telegram или Bitrix24.
    Параметр for_bitrix оставлен для совместимости, но не используется (Bitrix удален).
    """
    # Безопасно извлекаем данные, подставляя "не указано" если их нет
    parent_name = user_data.get('q1', "не указано")
    child_name = user_data.get('q2', "не указано")
    child_age = user_data.get('q3', "не указано")
    child_interests = user_data.get('q4', "не указаны")
    username = user_data.get('username', "N/A")

    # Формат для подтверждающего сообщения в Telegram
    return (
        f"Отлично, давайте всё проверим:\n\n"
        f"🙋‍♂️ Родитель: {parent_name}\n"
        f"👶 Ученик: {child_name}, {child_age} лет\n"
        f"🎮 Интересы: {child_interests}"
    )

def ensure_datetime(dt_value):
    """Гарантирует возврат datetime, даже если на входе строка"""
    if isinstance(dt_value, datetime):
        return dt_value
    elif isinstance(dt_value, str):
        try:
            return parser.isoparse(dt_value)
        except Exception:
            return None
    return None

# Универсальная зачистка временной зоны до naive UTC
def to_naive_utc(dt: datetime) -> datetime:
    """Делает datetime naive, но в UTC-секундах."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def as_moscow_time(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        # определяем локальная это МСК или UTC
        # предположим, что если в базе наивное и разница с now() < 4ч, то это МСК
        if abs((datetime.now() - dt).total_seconds()) < 5*3600:
            return dt.replace(tzinfo=ZoneInfo("Europe/Moscow"))
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Moscow"))
    return dt.astimezone(ZoneInfo("Europe/Moscow"))

def parse_moscow_datetime(dt_str: str) -> Optional[datetime]:
    dt = parse_datetime_iso(dt_str)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("Europe/Moscow"))
    else:
        return dt.astimezone(ZoneInfo("Europe/Moscow"))

