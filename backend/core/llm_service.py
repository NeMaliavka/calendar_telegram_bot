# backend/core/llm_service.py
import logging
import asyncio
import functools
import re
import ssl
from typing import List, Dict, Optional

from langchain_gigachat.chat_models import GigaChat
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.vectorstores import VectorStoreRetriever
from httpx import ConnectError, TimeoutException, HTTPStatusError

from backend import config
from backend.knowledge_base.loader import SYSTEM_PROMPT
from backend.utils.retry import async_retry

# Патч для отключения SSL проверки на уровне httpx
# Это необходимо для работы с GigaChat API в некоторых окружениях
try:
    import httpx
    # Создаем SSL контекст без проверки сертификатов
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Патчим httpx для использования нашего SSL контекста
    # Это будет применяться ко всем httpx клиентам, включая те, что используются в GigaChat
    original_ssl_context = getattr(httpx, '_default_ssl_context', None)
    if not original_ssl_context:
        # Сохраняем оригинальный контекст, если он есть
        pass
except Exception as e:
    logging.warning(f"Не удалось настроить SSL контекст для httpx: {e}")


CLASSIFIER_PROMPT = """
Отвечай ТОЛЬКО "да" или "нет".
Твоя задача - определить, относится ли запрос пользователя к деятельности онлайн-школы программирования.

ЗАПРОСЫ, НА КОТОРЫЕ ОТВЕТ "ДА":
- Приветствия и прощания (например, "Здравствуйте", "Привет", "Добрый день", "До свидания").
- Любые вопросы о курсах, ценах, расписании, пробных уроках.
- Прямые команды: "Записаться на урок", "Отменить запись", "Перенести встречу".
- Просьба позвать человека или менеджера.
- Нечеткие запросы, которые могут подразумевать интерес: "хочу попробовать", "как у вас тут".

ЗАПРОСЫ, НА КОТОРЫЕ ОТВЕТ "НЕТ":
- Случайный набор букв, бессмыслица.
- Вопросы на отвлеченные темы: "какая погода", "расскажи анекдот", "кто ты".
- Оскорбления или грубость.

ПРИМЕРЫ:
Пользователь: "Отменить запись"
Твой ответ: да
---
Пользователь: "ghbdtn"
Твой ответ: нет
---
Пользователь: "Хочу перенести пробный урок"
Твой ответ: да
"""

# Глобальная переменная для хранения ЕДИНСТВЕННОГО экземпляра клиента
_gigachat_instance: Optional[GigaChat] = None

eng = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
rus = "йцукенгшщзхъфывапролджэячсмитьбю"

def to_russian_layout(text):
    tbl = str.maketrans(eng + eng.upper(), rus + rus.upper())
    return text.translate(tbl)

def needs_layout_correction(text: str) -> bool:
    # Подсчёт латиницы и кириллицы
    latin = len(re.findall(r'[A-Za-z]', text))
    cyrillic = len(re.findall(r'[А-Яа-яЁё]', text))
    total_letters = latin + cyrillic

    # Переводим, если НЕТ кириллицы и есть латиница
    if cyrillic == 0 and latin > 0:
        return True

    # Переводим, если латинских букв хотя бы в 2 раза больше, чем кириллических
    if latin > 2 * cyrillic:
        return True

    # Переводим если очень короткое латинское слово (1-2 слова, только латиница)
    words = text.split()
    if len(words) <= 2 and all(re.fullmatch(r'[A-Za-z]+', w) for w in words):
        return True

    # Всё остальное оставляем как есть
    return False

# ✅ НОВАЯ АСИНХРОННАЯ ФУНКЦИЯ ДЛЯ СОЗДАНИЯ КЛИЕНТА
async def create_gigachat_instance() -> GigaChat:
    """
    Создает экземпляр GigaChat. В случае неудачи выбрасывает исключение.
    """
    import os
    # Отключаем проверку SSL на уровне окружения для всех HTTP клиентов
    os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
    
    logging.info("Попытка инициализации клиента GigaChat...")
    loop = asyncio.get_running_loop()
    giga_init_task = functools.partial(
        GigaChat,
        credentials=config.SBERCLOUD_API_KEY,
        scope="GIGACHAT_API_PERS",
        model=config.GIGACHAT_MODEL,
        max_tokens=config.GIGACHAT_MAX_TOKENS,
        verify_ssl_certs=False  # Отключаем проверку SSL для работы с GigaChat API
    )
    instance = await loop.run_in_executor(None, giga_init_task)
    logging.info(f"Основная модель GigaChat '{config.GIGACHAT_MODEL}' успешно инициализирована.")
    return instance

# ОБНОВЛЕННАЯ ФАБРИКА, ТЕПЕРЬ ОНА ТОЖЕ ASYNC
async def get_gigachat_client() -> Optional[GigaChat]:
    """
    Асинхронная фабрика-синглтон для клиента GigaChat.
    Обрабатывает отсутствие ключа и ошибки инициализации.
    """
    global _gigachat_instance
    if _gigachat_instance is not None:
        return _gigachat_instance

    # ✅ Шаг 1: Проверка ключа ДО вызова создания
    if not config.SBERCLOUD_API_KEY:
        logging.error("SBERCLOUD_API_KEY не задан. GigaChat client не будет инициализирован.")
        return None

    # ✅ Шаг 2: Обработка ошибок ПРИ вызове создания
    try:
        _gigachat_instance = await create_gigachat_instance()
        return _gigachat_instance
    except Exception as e:
        logging.error(f"Ошибка инициализации GigaChat: {e}", exc_info=True)
        _gigachat_instance = None  # Важно сбросить при ошибке
        return None

# --- AI-КОРРЕКТОР ---
async def correct_user_query(question: str) -> str:
    gigachat = await get_gigachat_client()
    if not gigachat:
        return question

    corrector_prompt = (
        "Ты — редактор-корректор. Исправь орфографические и грамматические ошибки в предложении, "
        "полностью сохранив его первоначальный смысл и стиль. Если ошибок нет, верни исходное предложение без изменений.\n"
        f"Предложение: '{question}'"
    )
    @async_retry(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=[ConnectError, TimeoutException, HTTPStatusError, Exception]
    )
    async def _invoke_corrector():
        response = await gigachat.ainvoke([SystemMessage(content=corrector_prompt)], 
                                          max_tokens=150)
        return response.content.strip()
    
    try:
        corrected_text = await _invoke_corrector()
        if corrected_text != question:
            logging.info(f"Запрос пользователя скорректирован: '{question}' -> '{corrected_text}'")
        return corrected_text
    except Exception as e:
        logging.error(f"Ошибка при коррекции запроса после всех попыток: {e}")
        return question
    
async def is_query_relevant_with_layout_correction(question: str, history: List[Dict[str, str]]) -> bool:
    relevant = await is_query_relevant_ai(question, history)
    if not relevant and needs_layout_correction(question):
        fixed_question = to_russian_layout(question)
        if fixed_question != question:
            logging.info(f"Попытка исправления раскладки: '{question}' -> '{fixed_question}'")
            relevant = await is_query_relevant_ai(fixed_question, history)
    return relevant

async def is_query_relevant_ai(question: str, history: List[Dict[str, str]]) -> bool:
    """
    Использует LLM с few-shot промптом для точной бинарной классификации релевантности запроса.
    """
    gigachat = await get_gigachat_client()
    if not gigachat:
        logging.warning("Пропуск проверки релевантности (сервис GigaChat недоступен). Разрешаем запрос.")
        return True  # В случае сбоя лучше пропустить запрос, чем блокировать пользователя

    last_assistant_message = ""
    if history and len(history) > 1 and history[-2]["role"] == "assistant":
        last_assistant_message = history[-2]["content"]

    # Формируем полный промпт для модели
    full_prompt = (
        f"{CLASSIFIER_PROMPT}\n\n"
        f"--- ДИАЛОГ ДЛЯ АНАЛИЗА ---\n"
        f"Последняя фраза ассистента: '{last_assistant_message}'\n"
        f"Новый запрос пользователя: '{question}'\n"
        f"--- КОНЕЦ ДИАЛОГА ---\n\n"
        f"Вопрос: Является ли новый запрос пользователя релевантным тематике школы? Ответь 'да' или 'нет'."
    )

    @async_retry(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=[ConnectError, TimeoutException, HTTPStatusError, Exception]
    )
    async def _invoke_classifier():
        response = await gigachat.ainvoke([SystemMessage(content=full_prompt)], max_tokens=3)
        return response.content.strip().lower()
    
    try:
        answer = await _invoke_classifier()
        logging.info(f"AI-классификатор ответил: '{answer}' для запроса '{question}'")
        return "да" in answer
    except Exception as e:
        error_str = str(e).lower()
        # Игнорируем SSL ошибки - разрешаем запрос
        if "ssl" in error_str or "certificate" in error_str:
            logging.warning(f"SSL ошибка при проверке релевантности после всех попыток: {e}. Разрешаем запрос по умолчанию.")
        else:
            logging.error(f"Ошибка при проверке релевантности после всех попыток: {e}. Разрешаем запрос по умолчанию.")
        return True # При любой ошибке лучше пропустить
    
    
# --- AI-ГЕНЕРАТОР ---
def _build_prompt(context: str, history: List[Dict[str, str]], context_key: str = "default") -> List[BaseMessage]:
    """
    Формирует промпт, добавляя в него указание на текущий контекст.
    """
    full_system_prompt = f"{SYSTEM_PROMPT}\n\n"

    # Добавляем AI прямое указание, на чем фокусироваться
    if context_key == "course_junior":
        full_system_prompt += "ВАЖНОЕ УКАЗАНИЕ: Клиент интересуется курсом для младшей группы (9-13 лет). Сосредоточь все ответы ИСКЛЮЧИТЕЛЬНО на этом курсе. Не упоминай другие курсы.\n\n"
    elif context_key == "course_senior":
        full_system_prompt += "ВАЖНОЕ УКАЗАНИЕ: Клиент интересуется курсом для старшей группы (14-17 лет). Сосредоточь все ответы ИСКЛЮЧИТЕЛЬНО на этом курсе. Не упоминай другие курсы.\n\n"

    full_system_prompt += (
        f"Опираясь на предоставленный ниже контекст, ответь на следующий вопрос пользователя.\n"
        f"--- КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ ---\n"
        f"{context}\n"
        f"--- КОНЕЦ КОНТЕКСТА ---"
    )
    
    messages: List[BaseMessage] = [SystemMessage(content=full_system_prompt)]
    
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
            
    return messages


async def get_llm_response(question: str, 
                           history: List[Dict[str, str]], 
                           retriever: VectorStoreRetriever, context_key: str = "default") -> str:
    """
    Получает развернутый ответ от "умной" LLM, учитывая контекст диалога.
    """
    gigachat = await get_gigachat_client()
    if not gigachat:
        return "Извините, сервис временно недоступен."

    @async_retry(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=[ConnectError, TimeoutException, HTTPStatusError, Exception]
    )
    async def _invoke_llm():
        # Шаг 1: Находим релевантные знания в документах
        docs = await retriever.ainvoke(question)
        context = "\n---\n".join([doc.page_content for doc in docs]) if docs else "Информация по данному вопросу в базе знаний отсутствует."

        # Шаг 2: Формируем правильный промпт, передавая контекст
        prompt_messages = _build_prompt(context, history, context_key)
        prompt_messages.append(HumanMessage(content=question))
        
        # Шаг 3: Делаем запрос к AI
        logging.info(f">>> Отправка запроса к GigaChat с контекстом '{context_key}'...")
        response = await gigachat.ainvoke(prompt_messages)
        return response
    
    try:
        response = await _invoke_llm()
        
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata:
            prompt_tokens = usage_metadata.get('prompt_tokens', 0)
            completion_tokens = usage_metadata.get('completion_tokens', 0)
            total_tokens = usage_metadata.get('total_tokens', 0)
            logging.info(
                f"<<< Получен ответ. Токены: {prompt_tokens} (запрос) + {completion_tokens} (ответ) = {total_tokens} (всего)"
            )
        else:
            logging.warning("Метаданные о токенах не найдены в ответе GigaChat.")
        
        return response.content.strip()
        
    except Exception as e:
        error_str = str(e).lower()
        # Логируем SSL ошибки отдельно
        if "ssl" in error_str or "certificate" in error_str:
            logging.error(f"SSL ошибка при обращении к GigaChat после всех попыток: {e}")
            logging.warning("Проверьте настройки SSL. Убедитесь, что verify_ssl_certs=False установлен.")
        else:
            logging.error(f"Ошибка при обращении к GigaChat после всех попыток: {e}", exc_info=True)
        return "К сожалению, произошла техническая ошибка. Пожалуйста, попробуйте позже."

