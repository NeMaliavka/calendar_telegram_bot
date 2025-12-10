import logging
import yaml
from pathlib import Path
import asyncio 
import functools 
from typing import Dict, Optional, List
import numpy as np
# Ленивый импорт sentence_transformers (только когда нужен)
def _get_sentence_transformer():
    """Ленивый импорт SentenceTransformer для избежания проблем с зависимостями."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer
    except ImportError as e:
        import logging
        logging.warning(f"Не удалось импортировать sentence_transformers: {e}")
        return None

# Ленивый импорт sklearn (только когда нужен)
def _get_cosine_similarity():
    """Ленивый импорт cosine_similarity для избежания проблем с зависимостями."""
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        return cosine_similarity
    except ImportError as e:
        logging.warning(f"Не удалось импортировать sklearn: {e}")
        return None


def load_keywords_from_yaml(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict): # Добавлена проверка на то, что это словарь
                logging.error(f"Файл YAML по пути {path} загружен, но его содержимое не является словарем.")
                return {}
            return data
    except FileNotFoundError: # Уточненная обработка ошибки
        logging.error(f"Файл YAML не найден по пути: {path}.")
        return {}
    except yaml.YAMLError as e: # Уточненная обработка ошибки синтаксиса YAML
        logging.error(f"Ошибка синтаксиса в YAML файле по пути: {path}. Ошибка: {e}")
        return {}
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при загрузке YAML файла по пути: {path}. Ошибка: {e}")
        return {}
    

class IntentRecognizer:
    """
    Гибридный сервис для распознавания намерений: сначала по правилам, затем по семантике.
    Использует единый YAML-файл как источник правды.
    """
    def __init__(self, keywords_path: str, model, threshold: float = 0.75):
        self.threshold = threshold
        self.model = model
        
        # Загружаем полную структуру из YAML
        self.intents_data = load_keywords_from_yaml(keywords_path)
        
        # Создаем эмбеддинги только на основе текстовых ключевых слов
        self.intents_embeddings = self._create_embeddings(self.intents_data)
        
        logging.info("Сервис IntentRecognizer успешно инициализирован с гибридной моделью.")

    # Асинхронная фабричная функция для создания экземпляра
    @staticmethod
    async def create(keywords_path: str, model_name: str = 'all-MiniLM-L6-v2', threshold: float = 0.75) -> 'IntentRecognizer':
        loop = asyncio.get_running_loop()
        logging.info(f"Начало асинхронной загрузки модели '{model_name}' для IntentRecognizer...")
        
        # ✅ Вот здесь мы асинхронно загружаем модель SentenceTransformer
        # Используем functools.partial для передачи аргументов
        SentenceTransformer = _get_sentence_transformer()
        if SentenceTransformer is None:
            raise ImportError("sentence_transformers не установлен. Установите: pip install sentence-transformers")
        
        model_instance = await loop.run_in_executor(
            None, functools.partial(SentenceTransformer, model_name)
        )
        logging.info("Модель SentenceTransformer для IntentRecognizer успешно загружена.")
        
        # ✅ Затем асинхронно инициализируем сам IntentRecognizer
        recognizer_instance = await loop.run_in_executor(
            None, functools.partial(IntentRecognizer, keywords_path, model=model_instance, threshold=threshold)
        )
        return recognizer_instance
    
    def _create_embeddings(self, intents_data: Dict[str, Dict]) -> Dict[str, np.ndarray]:
        """
        Создает эмбеддинги для семантического поиска, теперь работает с новой структурой YAML.
        """
        embedded_intents = {}
        for intent, data in intents_data.items():
            # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
            # Мы извлекаем список ключевых слов из ключа 'keywords'
            phrases = data.get('keywords', [])
            
            if phrases and isinstance(phrases, list):
                try:
                    embeddings = self.model.encode(phrases, convert_to_tensor=False)
                    embedded_intents[intent] = embeddings
                except Exception as e:
                    logging.error(f"Ошибка при создании эмбеддингов для интента '{intent}': {e}")
        return embedded_intents

    def _get_intent_by_rule(self, query: str) -> Optional[str]:
        """
        Первый слой: ищет точное вхождение ключевых фраз.
        """
        query_lower = query.lower()
        for intent, data in self.intents_data.items():
            # Ищем в списке 'keywords'
            for phrase in data.get('keywords', []):
                if phrase.lower() in query_lower:
                    logging.info(f"Интент '{intent}' определен по строгому правилу (фраза: '{phrase}').")
                    return intent
        return None

    def _get_intent_by_semantic(self, query: str) -> Optional[str]:
        """
        Второй слой: определяет интент с помощью семантического поиска.
        """
        if not self.intents_embeddings: return None
        
        query_embedding = self.model.encode([query])
        max_similarity = 0.0
        best_intent = None

        for intent, intent_embeddings in self.intents_embeddings.items():
            cosine_sim = _get_cosine_similarity()
            if cosine_sim is None:
                raise ImportError("sklearn не установлен. Установите: pip install scikit-learn")
            similarities = cosine_sim(query_embedding, intent_embeddings)[0]
            current_max_sim = np.max(similarities)
            
            if current_max_sim > max_similarity:
                max_similarity = current_max_sim
                best_intent = intent

        if max_similarity >= self.threshold:
            logging.info(f"Интент '{best_intent}' определен через семантику (схожесть: {max_similarity:.2f})")
            return best_intent
            
        return None

    def recognize(self, query: str) -> Optional[str]:
        """
        Главная функция: сначала правила, потом семантика.
        """
        rule_based_intent = self._get_intent_by_rule(query)
        if rule_based_intent:
            return rule_based_intent
            
        return self._get_intent_by_semantic(query)

