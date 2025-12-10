# backend/utils/retry.py
"""
Утилиты для retry логики с exponential backoff.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, Optional, List, Type
import time

T = TypeVar('T')

logger = logging.getLogger(__name__)


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Декоратор для повторных попыток выполнения асинхронных функций с exponential backoff.
    
    Args:
        max_attempts: Максимальное количество попыток (по умолчанию 3)
        initial_delay: Начальная задержка в секундах (по умолчанию 1.0)
        max_delay: Максимальная задержка в секундах (по умолчанию 60.0)
        exponential_base: База для экспоненциального роста задержки (по умолчанию 2.0)
        retryable_exceptions: Список исключений, при которых нужно повторять попытку
                             Если None, повторяет при любых исключениях
        on_retry: Функция-колбэк, вызываемая при каждой повторной попытке
                 Принимает (exception, attempt_number)
    
    Returns:
        Декорированная функция
    
    Example:
        @async_retry(max_attempts=3, initial_delay=1.0)
        async def call_api():
            # код вызова API
    """
    if retryable_exceptions is None:
        retryable_exceptions = [Exception]
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Проверяем, нужно ли повторять попытку
                    should_retry = any(isinstance(e, exc_type) for exc_type in retryable_exceptions)
                    
                    if not should_retry or attempt >= max_attempts:
                        # Не повторяем или достигли максимума попыток
                        logger.error(
                            f"[RETRY] Функция {func.__name__} завершилась ошибкой после {attempt} попыток: {e}"
                        )
                        raise
                    
                    # Вычисляем задержку с exponential backoff
                    delay = min(
                        initial_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    last_exception = e
                    
                    logger.warning(
                        f"[RETRY] Попытка {attempt}/{max_attempts} функции {func.__name__} не удалась: {e}. "
                        f"Повтор через {delay:.2f} сек."
                    )
                    
                    # Вызываем колбэк, если он есть
                    if on_retry:
                        try:
                            on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"[RETRY] Ошибка в колбэке on_retry: {callback_error}")
                    
                    # Ждем перед следующей попыткой
                    await asyncio.sleep(delay)
            
            # Если дошли сюда, все попытки исчерпаны
            logger.error(
                f"[RETRY] Функция {func.__name__} не удалась после {max_attempts} попыток. "
                f"Последняя ошибка: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Декоратор для повторных попыток выполнения синхронных функций с exponential backoff.
    
    Args:
        max_attempts: Максимальное количество попыток (по умолчанию 3)
        initial_delay: Начальная задержка в секундах (по умолчанию 1.0)
        max_delay: Максимальная задержка в секундах (по умолчанию 60.0)
        exponential_base: База для экспоненциального роста задержки (по умолчанию 2.0)
        retryable_exceptions: Список исключений, при которых нужно повторять попытку
        on_retry: Функция-колбэк, вызываемая при каждой повторной попытке
    
    Returns:
        Декорированная функция
    """
    if retryable_exceptions is None:
        retryable_exceptions = [Exception]
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Проверяем, нужно ли повторять попытку
                    should_retry = any(isinstance(e, exc_type) for exc_type in retryable_exceptions)
                    
                    if not should_retry or attempt >= max_attempts:
                        logger.error(
                            f"[RETRY] Функция {func.__name__} завершилась ошибкой после {attempt} попыток: {e}"
                        )
                        raise
                    
                    # Вычисляем задержку с exponential backoff
                    delay = min(
                        initial_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    last_exception = e
                    
                    logger.warning(
                        f"[RETRY] Попытка {attempt}/{max_attempts} функции {func.__name__} не удалась: {e}. "
                        f"Повтор через {delay:.2f} сек."
                    )
                    
                    # Вызываем колбэк, если он есть
                    if on_retry:
                        try:
                            on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"[RETRY] Ошибка в колбэке on_retry: {callback_error}")
                    
                    # Ждем перед следующей попыткой
                    time.sleep(delay)
            
            # Если дошли сюда, все попытки исчерпаны
            logger.error(
                f"[RETRY] Функция {func.__name__} не удалась после {max_attempts} попыток. "
                f"Последняя ошибка: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    return decorator

