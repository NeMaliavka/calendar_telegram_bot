# backend/services/rag_service.py 

import logging
from typing import List, Dict

# --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ИМПОРТИРУЕМ РЕАЛЬНУЮ ФУНКЦИЮ ---
# Вместо условных импортов, мы берем готовую функцию из вашего llm_service.
from backend.core.llm_service import get_llm_response

async def find_contextual_answer(user_query: str, history: List[Dict[str, str]], retriever) -> str | None:
    """
    Ищет ответ на вопрос, используя существующий сервис get_llm_response.
    """
    logging.info(f"[RAG] Начинаем глубокий поиск по документам для запроса: '{user_query}'")

    # Просто вызываем вашу готовую функцию, которая делает всю магию:
    # 1. Ищет контекст в векторной базе (vectorstore).
    # 2. Формирует промпт с системными инструкциями (SYSTEM_PROMPT).
    # 3. Отправляет все в GigaChat и возвращает ответ.
    final_answer = await get_llm_response(question=user_query, history=history, retriever=retriever)
    
    # Можно добавить проверку, чтобы не возвращать стандартные "заглушки"
    if "техническая ошибка" in final_answer or "сервис временно недоступен" in final_answer:
        logging.error(f"[RAG] Сервис GigaChat вернул ошибку: {final_answer}")
        return None

    return final_answer

