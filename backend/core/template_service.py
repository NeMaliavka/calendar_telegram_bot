import random
import yaml
import re
import logging
from typing import List, Dict, Tuple
from pathlib import Path
# Импортируем функцию для подсчета учеников
from backend.db.database import count_enrolled as get_enrolled_student_count

from backend.utils.text_tools import inflect_name

# Предполагается, что ваш файл templates.py находится здесь
# и в нем есть переменная TEMPLATES
try:
    from backend.knowledge_base.documents.templates import TEMPLATES
    logging.info(f"Файл templates.py успешно загружен.")
except ImportError:
    logging.error("Не удалось импортировать TEMPLATES из backend.knowledge_base.documents.templates")
    TEMPLATES = {}

INTENT_KEYWORDS = {}
try:
    # Строим правильный путь к файлу keywords.yaml
    # Path(__file__) -> backend/core/template_service.py
    # .parent.parent -> backend/
    # .parent.parent.parent -> корень проекта
    config_path = Path(__file__).parent.parent.parent / 'config' / 'keywords.yaml'
    if not config_path.exists():
        # Пробуем альтернативный путь
        config_path = Path(__file__).parent.parent.parent / 'backend' / 'knowledge_base' / 'rules' / 'keywords.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            INTENT_KEYWORDS = yaml.safe_load(f)
        logging.info(f"Файл keywords.yaml из '{config_path}' успешно загружен.")
    else:
        logging.warning(f"Файл keywords.yaml не найден по пути: {config_path}")
except Exception as e:
    logging.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить keywords.yaml. {e}")

def find_template_by_keywords(query_text: str) -> Tuple[str, dict | None] | tuple[None, None]:
    """
    Ищет интент и соответствующий ему шаблон, используя единую базу keywords.yaml.
    Умеет искать как по ключевым словам (для текста), так и по точным ключам (для кнопок).
    """
    query_lower = query_text.lower()
    logging.info(f"--- НАЧАЛО ПОИСКА ШАБЛОНА для запроса: '{query_lower}' ---")

    # --- ДОБАВЛЕННЫЙ БЛОК: прямое сопоставление как интент ---
    # ПРИОРИТЕТ 1: Сначала ищем прямой ключ в TEMPLATES.
    # Это самый надежный способ для кнопок, передающих точный интент.
    if query_text in TEMPLATES:
        logging.info(f"✅ УСПЕХ: '{query_text}' распознан как интент, найден шаблон напрямую.")
        return query_text, TEMPLATES.get(query_text)
    
    # ПРИОРИТЕТ 2: Если прямого совпадения нет, ищем по keywords.yaml (для текстовых сообщений).
    for intent, data in INTENT_KEYWORDS.items():
        logging.debug(f"Проверяю интент: '{intent}'...")
        # Сначала проверяем точное совпадение по ключу от кнопки
        if 'callback_keys' in data and query_lower in data.get('callback_keys', []):
            logging.info(f"✅ УСПЕХ: Найден интент '{intent}' по точному ключу кнопки '{query_lower}'.")
            template = TEMPLATES.get(intent)
            return (intent, template) if template else (None, None)

        # Поиск по ключевым словам для текстовых запросов
        for keyword in data.get('keywords', []):
            if keyword in query_lower:
                logging.info(f"✅ УСПЕХ: Найден интент '{intent}' по ключевому слову '{keyword}'.")
                template = TEMPLATES.get(intent)
                if template:
                    logging.info(f"Шаблон для интента '{intent}' успешно найден в TEMPLATES.")
                    return intent, template
                else:
                    logging.error(f"КРИТИЧЕСКАЯ ОШИБКА: Интент '{intent}' есть в keywords.yaml, но для него нет шаблона в TEMPLATES!")
                    return None, None

    
    logging.warning(f"❌ ПРОВАЛ: Не удалось найти интент для запроса: '{query_text}' после проверки всех правил.")
    logging.info("--- КОНЕЦ ПОИСКА ШАБЛОНА ---")
    return None, None

async def build_template_response(template_data: dict | list, 
                                  history: List[Dict], user_data: dict) -> str:
    """
    Собирает "умный" ответ из шаблона, анализируя историю, данные пользователя и счетчик учеников.
    """
    # Сначала обработаем самые простые случаи
    if isinstance(template_data, str):
        # Если шаблон - это просто строка, сразу ее и возвращаем
        return template_data
    
    if isinstance(template_data, list):
        # Если это список, выбираем случайный ответ
        return random.choice(template_data)

    if isinstance(template_data, dict):
        response_parts = []
        enrolled_count = await get_enrolled_student_count()

        if greetings := template_data.get("greeting"):
            response_parts.append(random.choice(greetings))

        if default_body := template_data.get("body"):
            response_parts.append(default_body)

        # Выбираем правильный основной текст в зависимости от статуса акции
        if enrolled_count < 100 and (promo_body := template_data.get("body_promo_active")):
            response_parts.append(promo_body)
        elif enrolled_count >= 100 and (ended_promo_body := template_data.get("body_promo_ended")):
            response_parts.append(ended_promo_body)

        if follow_ups := template_data.get("follow_up"):
            response_parts.append(random.choice(follow_ups))

        full_response_template = "\n\n".join(filter(None, response_parts))

        # --- ЛОГИКА ОБРАБОТКИ ПЛЕЙСХОЛДЕРОВ ---
        def replace_placeholder(match):
            placeholder = match.group(1)
            parts = placeholder.split(':')
            var_name = parts[0]  # например, 'child_name'
            case = parts[1] if len(parts) > 1 else None  # например, 'datv' или None

            # Подставляем имя родителя по умолчанию, если оно не найдено
            if var_name == 'parent_name' and not user_data.get(var_name):
                 value = "Уважаемый родитель"
            else:
                value = user_data.get(var_name, '')
            
            # Если указан падеж и есть значение, склоняем его
            if case and value:
                return inflect_name(value, case)
            else:
                return str(value)

        # Находим все плейсхолдеры вида {variable:case} или {variable} и заменяем их
        processed_response = re.sub(r'\{([^}]+)\}', replace_placeholder, full_response_template)
        
        return processed_response
        
    return "Не удалось сформировать ответ по шаблону."

