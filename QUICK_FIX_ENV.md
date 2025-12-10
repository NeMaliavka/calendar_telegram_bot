# Быстрое исправление .env файла

## Проблема
В текущем `.env` файле отсутствуют:
- `DATABASE_URL`
- `SBERCLOUD_API_KEY`

## Решение

### Вариант 1: Запустить скрипт (самый быстрый)

В PowerShell выполните:
```powershell
.\UPDATE_ENV.ps1
```

### Вариант 2: Вручную добавить в .env

Откройте файл `.env` и добавьте в конец:

```env
# ==== GigaChat AI ====
SBERCLOUD_API_KEY=NmMyNmM3MDEtZGI4My00OTc1LThkZTMtOTVmZjljZWNjOWE2OjE4NzFiYzNjLTE0ZGQtNGFiYi1iZTFlLWZkZWViNGNiYmFiMQ==
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_MAX_TOKENS=800

# ==== PostgreSQL Database ====
DATABASE_URL=postgresql+asyncpg://gen_user:RozaChainaia01.@5d4cf0a44c31f942275b6490.twc1.net:5432/default_db

# ==== База знаний (RAG) ====
CHROMA_DB_PATH=backend/db/chroma_db
PROMPT_PATH=backend/knowledge_base/documents/lor.txt
KEYWORDS_PATH=config/keywords.yaml
DISTANCE_THRESHOLD=0.9
```

### Вариант 3: Полная замена .env

Выполните в PowerShell:
```powershell
@"
# ==== Telegram Tokens ====
TELEGRAM_BOT_TOKEN=7695557877:AAF6EalkJlLMg67Y7bB6_lqHid4CEbWdAYY
ADMIN_TELEGRAM_BOT_TOKEN=8122387134:AAHThmy0beIvd4W6AAOQsolBvHq_Hi9VVik
ADMIN_IDS=2007815494

# ==== Google Calendar ====
GOOGLE_CALENDAR_ACTIVATE=True
GOOGLE_CREDENTIALS_PATH=./nobugs-478214-0d41160b4771.json
GOOGLE_CALENDAR_ID=nobugscoding@gmail.com

# ==== Google Sheets ====
GOOGLE_SHEETS_ACTIVATE=True
GOOGLE_SHEETS_ID=1-_syjwdqi0fX9IFwsK8umFgNewImr4GokGo-0c6N6iA
GOOGLE_SHEETS_NAME=Лист1

# ==== GigaChat AI ====
SBERCLOUD_API_KEY=NmMyNmM3MDEtZGI4My00OTc1LThkZTMtOTVmZjljZWNjOWE2OjE4NzFiYzNjLTE0ZGQtNGFiYi1iZTFlLWZkZWViNGNiYmFiMQ==
GIGACHAT_MODEL=GigaChat-Pro
GIGACHAT_MAX_TOKENS=800

# ==== PostgreSQL Database ====
DATABASE_URL=postgresql+asyncpg://gen_user:RozaChainaia01.@5d4cf0a44c31f942275b6490.twc1.net:5432/default_db

# ==== База знаний (RAG) ====
CHROMA_DB_PATH=backend/db/chroma_db
PROMPT_PATH=backend/knowledge_base/documents/lor.txt
KEYWORDS_PATH=config/keywords.yaml
DISTANCE_THRESHOLD=0.9

# ==== Рабочие часы ====
START_HOUR=9
END_HOUR=18
SLOT_DURATION=60
TIMEZONE=Europe/Moscow

# ==== Environment ====
ENVIRONMENT=production
LOG_LEVEL=INFO
"@ | Out-File -FilePath .env -Encoding utf8
```

## После обновления .env:

1. **Переустановите зависимости** (для исправления numpy):
```bash
pip install --upgrade -r requirements.txt
```

2. **Запустите бота**:
```bash
python run_bot.py
```

## Проверка

После обновления проверьте:
```bash
python -c "from backend import config; print('DATABASE_URL:', bool(config.DATABASE_URL)); print('SBERCLOUD_API_KEY:', bool(config.SBERCLOUD_API_KEY))"
```

Оба должны быть `True`.

