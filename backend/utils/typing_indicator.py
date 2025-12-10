# backend/utils/typing_indicator.py
"""
Утилита для отображения индикатора "печатает" во время долгих операций.
"""

import asyncio
import logging
from typing import Optional
from aiogram import Bot
from aiogram.enums import ChatAction

logger = logging.getLogger(__name__)


async def show_typing_indicator(
    bot: Bot,
    chat_id: int,
    duration: Optional[float] = None,
    action: ChatAction = ChatAction.TYPING
):
    """
    Показывает индикатор "печатает" в течение указанного времени или до отмены.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        duration: Длительность показа индикатора в секундах (None = бесконечно)
        action: Тип действия (TYPING, UPLOAD_PHOTO, UPLOAD_VIDEO и т.д.)
    
    Returns:
        Task, которую можно отменить через task.cancel()
    """
    async def _keep_typing():
        try:
            while True:
                await bot.send_chat_action(chat_id=chat_id, action=action)
                await asyncio.sleep(3)  # Telegram требует обновлять каждые 3-5 секунд
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Ошибка при отправке typing indicator: {e}")
    
    if duration:
        # Если указана длительность, запускаем на определенное время
        async def _timed_typing():
            try:
                end_time = asyncio.get_event_loop().time() + duration
                while asyncio.get_event_loop().time() < end_time:
                    await bot.send_chat_action(chat_id=chat_id, action=action)
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"Ошибка при отправке typing indicator: {e}")
        
        task = asyncio.create_task(_timed_typing())
    else:
        # Если длительность не указана, запускаем бесконечно (нужно будет отменить вручную)
        task = asyncio.create_task(_keep_typing())
    
    return task


class TypingContext:
    """
    Контекстный менеджер для автоматического управления индикатором печати.
    
    Usage:
        async with TypingContext(bot, chat_id):
            # Долгая операция
            await some_long_operation()
    """
    
    def __init__(self, bot: Bot, chat_id: int, action: ChatAction = ChatAction.TYPING):
        self.bot = bot
        self.chat_id = chat_id
        self.action = action
        self.task: Optional[asyncio.Task] = None
    
    async def __aenter__(self):
        self.task = await show_typing_indicator(self.bot, self.chat_id, action=self.action)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Ошибка при отмене typing indicator: {e}")

