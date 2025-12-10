"""
Главный файл бота - инициализация и запуск
"""
import logging
import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from backend.services.calendar_service import CalendarService
from backend.services.booking_service import BookingService
from backend.handlers import commands, callbacks, menu, reschedule_cancel
from backend import config

# Импорты для БД и ИИ
from backend.db.database import init_db, db_ping
from backend.core.llm_service import get_gigachat_client
from backend.knowledge_base.loader import get_vectorstore_async
from backend.services.intent_recognizer import IntentRecognizer

# Импорт scheduler
from backend.scheduler import router as scheduler_router

# Настройка кодировки для Windows
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Перезаписываем существующую конфигурацию
)
logger = logging.getLogger(__name__)

# Проверка обязательных настроек
if not config.BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

if not config.GOOGLE_CALENDAR_ACTIVATE:
    logger.warning("Google Calendar не активирован! Бот будет работать в режиме ограниченной функциональности.")

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация сервисов
calendar_service = None
booking_service = None

# ИИ-сервисы
vectorstore = None
retriever = None
intent_recognizer = None

try:
    if config.GOOGLE_CALENDAR_ACTIVATE:
        calendar_service = CalendarService()
        booking_service = BookingService()
        logger.info("Сервисы Google Calendar успешно инициализированы")
except Exception as e:
    logger.error(f"Ошибка при инициализации сервисов: {e}")
    logger.warning("Бот запустится без функционала календаря")


async def init_database():
    """Инициализация базы данных"""
    try:
        if not config.DATABASE_URL:
            logger.warning("DATABASE_URL не установлен. БД не будет инициализирована.")
            return False
        
        logger.info("Инициализация базы данных...")
        await init_db()
        await db_ping()
        logger.info("✅ База данных успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации БД: {e}", exc_info=True)
        return False


async def init_ai_services():
    """Инициализация ИИ-сервисов (GigaChat, RAG, IntentRecognizer)"""
    global vectorstore, retriever, intent_recognizer
    
    try:
        # Инициализация GigaChat
        if config.SBERCLOUD_API_KEY:
            logger.info("Инициализация GigaChat...")
            gigachat_client = await get_gigachat_client()
            if gigachat_client:
                logger.info("✅ GigaChat успешно инициализирован")
            else:
                logger.warning("⚠️ GigaChat не удалось инициализировать (проверьте SBERCLOUD_API_KEY)")
        else:
            logger.warning("SBERCLOUD_API_KEY не установлен. GigaChat не будет работать.")
        
        # Инициализация векторной базы знаний (RAG)
        try:
            logger.info("Инициализация векторной базы знаний...")
            vectorstore = await get_vectorstore_async()
            retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
            logger.info("✅ Векторная база знаний успешно загружена")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить векторную базу знаний: {e}")
            logger.warning("RAG будет работать в ограниченном режиме")
        
        # Инициализация IntentRecognizer
        try:
            keywords_path = config.KEYWORDS_PATH
            if keywords_path:
                logger.info(f"Инициализация IntentRecognizer (keywords: {keywords_path})...")
                intent_recognizer = await IntentRecognizer.create(
                    keywords_path=keywords_path,
                    model_name='all-MiniLM-L6-v2',
                    threshold=config.DISTANCE_THRESHOLD
                )
                logger.info("✅ IntentRecognizer успешно инициализирован")
            else:
                logger.warning("KEYWORDS_PATH не установлен. IntentRecognizer не будет работать.")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось инициализировать IntentRecognizer: {e}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации ИИ-сервисов: {e}", exc_info=True)
        return False


# Регистрация обработчиков
def setup_handlers():
    """Настройка всех обработчиков"""
    # Команды
    commands.setup_commands_handlers(dp, calendar_service, booking_service)
    
    # Callback обработчики
    callbacks.setup_callbacks_handlers(dp, calendar_service, booking_service)
    
    # Меню обработчики
    menu.setup_menu_handlers(dp, calendar_service, booking_service)
    
    # Обработчики переноса и отмены
    reschedule_cancel.setup_reschedule_cancel_handlers(dp, calendar_service, booking_service)
    
    # Новые handlers для БД и ИИ
    from backend.handlers import sales_funnel, onboarding_handlers, waitlist_handlers, check_booking_handlers
    dp.include_router(sales_funnel.router)
    dp.include_router(onboarding_handlers.router)
    dp.include_router(waitlist_handlers.router)
    dp.include_router(check_booking_handlers.router)
    
    logger.info("Все обработчики зарегистрированы")


async def setup_bot_commands():
    """Настройка бокового меню команд бота"""
    commands_list = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="booking", description="✍️ Записаться на пробный урок"),
        BotCommand(command="my_lessons", description="🗓️ Мои записи"),
        BotCommand(command="reschedule", description="🔄 Перенести запись"),
        BotCommand(command="cancel", description="❌ Отменить запись"),
        BotCommand(command="faq", description="💬 Частые вопросы"),
        BotCommand(command="community_tg", description="🔗 Наш Telegram"),
        BotCommand(command="community_vk", description="🔗 Наш ВКонтакте"),
    ]
    
    try:
        await bot.set_my_commands(commands_list)
        logger.info("✅ Боковое меню команд установлено")
    except Exception as e:
        logger.error(f"Ошибка при установке команд меню: {e}", exc_info=True)


async def main():
    """Главная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("Запуск бота...")
    logger.info(f"Режим: {config.ENVIRONMENT}")
    logger.info(f"Google Calendar: {'Активирован' if config.GOOGLE_CALENDAR_ACTIVATE else 'Отключен'}")
    logger.info("=" * 50)
    
    if not config.BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
    
    if not config.GOOGLE_CALENDAR_ACTIVATE:
        logger.warning("[WARN] Google Calendar отключен. Бот будет работать в ограниченном режиме.")
    
    # Инициализация базы данных
    db_initialized = await init_database()
    if not db_initialized:
        logger.warning("[WARN] База данных не инициализирована. Некоторые функции могут не работать.")
    
    # Инициализация ИИ-сервисов
    ai_initialized = await init_ai_services()
    if not ai_initialized:
        logger.warning("[WARN] ИИ-сервисы не инициализированы. Некоторые функции могут не работать.")
    
    # Сохраняем retriever и intent_recognizer в bot для доступа в handlers
    if retriever:
        bot.retriever = retriever
    if intent_recognizer:
        bot.intent_recognizer = intent_recognizer
    
    # Настраиваем боковое меню команд
    await setup_bot_commands()
    
    # Настраиваем обработчики
    setup_handlers()
    
    # Регистрируем scheduler router
    dp.include_router(scheduler_router)
    logger.info("Scheduler router зарегистрирован")
    
    # Проверяем подключение перед запуском
    try:
        logger.info("Проверка подключения к Telegram API...")
        me = await bot.get_me()
        logger.info(f"[OK] Бот подключен: @{me.username} (ID: {me.id})")
    except Exception as e:
        logger.error(f"[ERROR] Не удалось подключиться к Telegram API: {e}", exc_info=True)
        await bot.session.close()
        return
    
    # Удаляем webhook, если он был установлен (для предотвращения конфликтов)
    try:
        logger.info("Проверка и удаление webhook (если установлен)...")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("[OK] Webhook удален (если был установлен)")
    except Exception as e:
        logger.warning(f"[WARN] Не удалось удалить webhook (возможно, его не было): {e}")
    
    # Запускаем polling
    try:
        logger.info("Запуск polling...")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
