"""
Независимый runner для scheduler задач
Запускается в отдельном контейнере для фоновых задач
"""
import asyncio
import logging
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend import config
from backend.scheduler.tasks import check_and_send_reminders, check_completed_lessons

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def main():
    """
    Основная функция для независимого запуска планировщика.
    """
    logger.info("=" * 50)
    logger.info("Запуск независимого процесса планировщика...")
    logger.info("=" * 50)
    
    if not config.BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен. Планировщик не может работать.")
        sys.exit(1)
    
    # Создаем объект Bot для отправки сообщений
    bot = Bot(token=config.BOT_TOKEN)
    
    # Создаем планировщик с московским временем
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    
    # Добавляем задачу проверки напоминаний (каждую минуту)
    scheduler.add_job(
        check_and_send_reminders,
        'interval',
        minutes=1,
        args=(bot,),
        id='check_and_send_reminders',
        replace_existing=True,
        misfire_grace_time=30,
        max_instances=1
    )
    
    # Добавляем задачу проверки завершенных уроков (каждые 5 минут)
    scheduler.add_job(
        check_completed_lessons,
        'interval',
        minutes=5,
        args=(bot,),
        id='check_and_mark_completed_lessons',
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1
    )
    
    # Запускаем планировщик
    scheduler.start()
    logger.info("✅ Планировщик запущен и готов к работе.")
    logger.info("   - Проверка напоминаний: каждую минуту")
    logger.info("   - Проверка завершенных уроков: каждые 5 минут")
    
    # Основной цикл - держим процесс живым
    try:
        while True:
            await asyncio.sleep(3600)  # Спим час, чтобы не нагружать процессор
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Критическая ошибка в планировщике: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Планировщик остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

