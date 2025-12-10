# Настройка .env файла

## Проблема

Бот не может найти файл `.env` с настройками. 

## Решение

Создайте файл `.env` в корне проекта (`C:\Users\Алиса\Desktop\calendar\.env`) со следующим содержимым:

```env
# ==== Telegram Tokens ====
TELEGRAM_BOT_TOKEN=8401224058:AAHgif8-G4KTwEDgqtChnemAxfzuEPdUk00
ADMIN_TELEGRAM_BOT_TOKEN=8122387134:AAHThmy0beIvd4W6AAOQsolBvHq_Hi9VVik
ADMIN_IDS=2007815494

# ==== Google Calendar ====
GOOGLE_CALENDAR_ACTIVATE=True
GOOGLE_CREDENTIALS_PATH=./nobugs-478214-0d41160b4771.json
GOOGLE_CALENDAR_ID=nobugscoding@gmail.com

# ==== Рабочие часы ====
START_HOUR=9
END_HOUR=18
SLOT_DURATION=60
TIMEZONE=Europe/Moscow

# ==== Environment ====
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Быстрая команда для создания файла

В PowerShell:
```powershell
@"
TELEGRAM_BOT_TOKEN=8401224058:AAHgif8-G4KTwEDgqtChnemAxfzuEPdUk00
ADMIN_TELEGRAM_BOT_TOKEN=8122387134:AAHThmy0beIvd4W6AAOQsolBvHq_Hi9VVik
ADMIN_IDS=2007815494
GOOGLE_CALENDAR_ACTIVATE=True
GOOGLE_CREDENTIALS_PATH=./nobugs-478214-0d41160b4771.json
GOOGLE_CALENDAR_ID=nobugscoding@gmail.com
START_HOUR=9
END_HOUR=18
SLOT_DURATION=60
TIMEZONE=Europe/Moscow
ENVIRONMENT=production
LOG_LEVEL=INFO
"@ | Out-File -FilePath .env -Encoding utf8
```

После создания файла запустите бота снова:
```bash
python run_bot.py
```

