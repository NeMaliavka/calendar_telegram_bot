# ✅ Чеклист для запуска бота

## Перед запуском проверьте:

### 1. Обязательные настройки в `.env`:

```env
# Telegram
TELEGRAM_BOT_TOKEN=ваш_токен
ADMIN_IDS=ваш_telegram_id

# Google Calendar (если используется)
GOOGLE_CALENDAR_ACTIVATE=True
GOOGLE_CREDENTIALS_PATH=./nobugs-478214-0d41160b4771.json
GOOGLE_CALENDAR_ID=nobugscoding@gmail.com

# База данных PostgreSQL (ОБЯЗАТЕЛЬНО для работы с БД)
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database

# GigaChat (опционально, для ИИ)
SBERCLOUD_API_KEY=ваш_ключ_gigachat

# База знаний (опционально)
CHROMA_DB_PATH=backend/db/chroma_db
PROMPT_PATH=backend/knowledge_base/documents/lor.txt
KEYWORDS_PATH=config/keywords.yaml
```

### 2. Установите зависимости:

```bash
pip install -r requirements.txt
```

### 3. Опциональные файлы (бот будет работать и без них):

- `backend/knowledge_base/documents/lor.txt` - системный промпт для ИИ
- `config/keywords.yaml` или `backend/knowledge_base/rules/keywords.yaml` - ключевые слова для IntentRecognizer
- `backend/knowledge_base/documents/templates.py` - шаблоны ответов

**Важно:** Бот будет работать даже без этих файлов, но некоторые функции ИИ могут быть недоступны.

### 4. Запуск:

```bash
python run_bot.py
```

или

```bash
python backend/bot.py
```

## Что будет работать:

✅ **Базовый функционал:**
- Команды `/start`, `/book`, `/my_lessons`, `/reschedule`, `/cancel`
- Работа с Google Calendar (если активирован)
- Работа с Google Sheets (если активирован)

✅ **С БД (если DATABASE_URL установлен):**
- Сохранение пользователей и их данных
- Сохранение бронирований в БД
- История диалогов
- Онбординг пользователей

✅ **С ИИ (если SBERCLOUD_API_KEY установлен):**
- GigaChat для ответов на вопросы
- RAG-поиск по базе знаний (если файлы есть)
- Распознавание намерений (если keywords.yaml есть)

⚠️ **Бот будет работать даже если:**
- Нет DATABASE_URL (но БД функции не будут работать)
- Нет SBERCLOUD_API_KEY (но ИИ функции не будут работать)
- Нет файлов базы знаний (но RAG не будет работать)

## Возможные ошибки при первом запуске:

1. **"DATABASE_URL не установлен"** - это предупреждение, не ошибка. БД функции просто не будут работать.

2. **"SBERCLOUD_API_KEY не установлен"** - это предупреждение, не ошибка. ИИ функции просто не будут работать.

3. **"Файл keywords.yaml не найден"** - это предупреждение. IntentRecognizer не будет работать, но бот запустится.

4. **"Файл templates.py не найден"** - это предупреждение. Шаблоны ответов не будут работать.

5. **Ошибки импорта** - проверьте, что установлены все зависимости из `requirements.txt`

## Рекомендации:

1. **Для полной функциональности** установите все переменные в `.env`
2. **Для тестирования** можно запустить только с Telegram токеном - базовые команды будут работать
3. **База данных** будет создана автоматически при первом запуске (если DATABASE_URL указан)

