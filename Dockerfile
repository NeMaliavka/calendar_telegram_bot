# Dockerfile для Telegram бота с ИИ и Google Calendar интеграцией

# Используем официальный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
# build-essential нужен для компиляции некоторых Python пакетов
# libpq-dev нужен для PostgreSQL клиента
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip

# Сначала копируем только requirements.txt
# Это ускоряет сборку при изменении кода
COPY requirements.txt .

# Устанавливаем Python зависимости
# Используем --no-cache-dir для уменьшения размера образа
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Создаем директории для данных
RUN mkdir -p /app/backend/db/chroma_db /app/logs

# Устанавливаем переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ANONYMIZED_TELEMETRY=False

# Команда по умолчанию (можно переопределить в docker-compose)
CMD ["python", "run_bot.py"]

