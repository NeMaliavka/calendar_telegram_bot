"""
Утилиты для работы с датами и форматированием
"""
from datetime import datetime
import pytz
from backend import config


def parse_datetime_from_string(dt_string: str) -> datetime:
    """
    Парсит datetime из строки ISO формата
    
    Args:
        dt_string: Строка в формате ISO
        
    Returns:
        Объект datetime
    """
    timezone = pytz.timezone(config.TIMEZONE)
    dt = datetime.fromisoformat(dt_string)
    if dt.tzinfo is None:
        dt = timezone.localize(dt)
    return dt
