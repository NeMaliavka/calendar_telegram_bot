# Полная настройка .env файла

## Текущие проблемы и решения

### 1. DATABASE_URL не установлен
**Решение:** Добавьте в `.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
```

### 2. SBERCLOUD_API_KEY не установлен
**Решение:** Добавьте в `.env`:
```env
SBERCLOUD_API_KEY=ваш_ключ_gigachat
```

### 3. numpy.dtype size changed (несовместимость версий)
**Решение:** Переустановите зависимости:
```bash
pip uninstall numpy pandas scikit-learn sentence-transformers -y
pip install numpy==1.24.3 pandas==2.0.3 scikit-learn==1.3.0 sentence-transformers==2.2.2
```

Или обновите все:
```bash
pip install --upgrade -r requirements.txt
```

## Полный пример .env файла

```env
# ==== Telegram Tokens ====
TELEGRAM_BOT_TOKEN=8401224058:AAHgif8-G4KTwEDgqtChnemAxfzuEPdUk00
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

# ==== База данных PostgreSQL (ОПЦИОНАЛЬНО) ====
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/calendar_bot

# ==== GigaChat AI (ОПЦИОНАЛЬНО) ====
SBERCLOUD_API_KEY=ваш_ключ_gigachat

# ==== База знаний (уже настроено) ====
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
```

## После настройки

1. Переустановите зависимости (для исправления numpy):
```bash
pip install --upgrade -r requirements.txt
```

2. Запустите бота:
```bash
python run_bot.py
```

## Статус файлов

✅ **lor.txt** - подключен (7042 символа)
✅ **templates.py** - подключен (23 элемента)
✅ **keywords.yaml** - подключен (14 элементов)

Все файлы читаются корректно!

