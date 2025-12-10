import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения из файла .env
load_dotenv()
# # Загружаем .env из корня проекта
# env_path = Path(__file__).parent.parent / '.env'
# if env_path.exists():
#     load_dotenv(env_path, override=True)
# else:
#     # Пробуем загрузить из текущей директории
#     load_dotenv(override=True)

# Настройка SSL-сертификата (если необходимо)
# Для работы с GigaChat API может потребоваться отключение проверки SSL
# или установка специального сертификата
CERT_FILENAME = "russian_trusted_root_ca.cer"
cert_path = Path(__file__).parent.parent / CERT_FILENAME
if cert_path.exists():
    os.environ["SSL_CERT_FILE"] = str(cert_path)
    logging.info(f"SSL-сертификат найден и установлен: {cert_path}")
else:
    logging.warning(f"SSL-сертификат не найден по пути: {cert_path}. Будет использоваться отключение проверки SSL.")


# Telegram Bot
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_TELEGRAM_BOT_TOKEN', '')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Google Calendar
GOOGLE_CALENDAR_ACTIVATE = os.getenv('GOOGLE_CALENDAR_ACTIVATE', 'False').lower() == 'true'
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', './google-credentials.json')
GOOGLE_CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', '')

# Google Sheets
GOOGLE_SHEETS_ACTIVATE = os.getenv('GOOGLE_SHEETS_ACTIVATE', 'False').lower() == 'true'
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID', '')
GOOGLE_SHEETS_NAME = os.getenv('GOOGLE_SHEETS_NAME', 'Записи')

# Рабочие часы
START_HOUR = int(os.getenv('START_HOUR', '9'))
END_HOUR = int(os.getenv('END_HOUR', '18'))

# Часовой пояс
TIMEZONE = os.getenv('TIMEZONE', 'Europe/Moscow')

# Длительность слота (в минутах)
SLOT_DURATION = int(os.getenv('SLOT_DURATION', '60'))

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# PostgreSQL Database
DATABASE_URL = os.getenv("DATABASE_URL")
# Формат: postgresql+asyncpg://user:password@host:port/database

# GigaChat AI
SBERCLOUD_API_KEY = os.getenv("SBERCLOUD_API_KEY")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-Pro")
GIGACHAT_MAX_TOKENS = int(os.getenv("GIGACHAT_MAX_TOKENS", "1024"))

# База знаний (опционально, если нужен RAG)
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "backend/db/chroma_db")
PROMPT_PATH = os.getenv("PROMPT_PATH", "backend/knowledge_base/documents/lor.txt")
KEYWORDS_PATH = os.getenv("KEYWORDS_PATH", "config/keywords.yaml")
DISTANCE_THRESHOLD = float(os.getenv("DISTANCE_THRESHOLD", "0.9"))

