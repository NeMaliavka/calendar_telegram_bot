import os
import asyncio
import logging
import functools
from typing import List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_chroma import Chroma

from backend import config

# Отключаем телеметрию PostHog для ChromaDB
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("DO_NOT_TRACK", "1")

# Ленивый импорт sentence_transformers (только когда нужен)
def _get_sentence_transformer():
    """Ленивый импорт SentenceTransformer для избежания проблем с зависимостями."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer
    except ImportError as e:
        logging.warning(f"Не удалось импортировать sentence_transformers: {e}")
        return None

# Пути к файлам с информацией о проекте
DOCUMENTS_PATHS = [
    "backend/knowledge_base/documents/project_info.pdf",
    "backend/knowledge_base/documents/lor.txt"
]

class FridaEmbeddings:
    def __init__(self, model: Any):
        self.model = model

    @staticmethod
    async def create(model_name: str = "ai-forever/FRIDA") -> 'FridaEmbeddings':
        SentenceTransformer = _get_sentence_transformer()
        if SentenceTransformer is None:
            raise ImportError("sentence_transformers не установлен. Установите: pip install sentence-transformers")
        
        loop = asyncio.get_running_loop()
        logging.info(f"Начало асинхронной загрузки модели '{model_name}'...")
        model_instance = await loop.run_in_executor(None, SentenceTransformer, model_name)
        logging.info("Модель успешно загружена.")
        return FridaEmbeddings(model_instance)

    async def embed_query(self, text: str) -> List[float]:
        loop = asyncio.get_running_loop()
        encode_task = functools.partial(self.model.encode, f"search_query: {text}", normalize_embeddings=True)
        return (await loop.run_in_executor(None, encode_task)).tolist()

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_running_loop()

        def _embed_all():
            return [self.model.encode(f"search_document: {t}", normalize_embeddings=True).tolist() for t in texts]

        return await loop.run_in_executor(None, _embed_all)


class SyncFridaEmbeddings:
    def __init__(self, async_embeddings: FridaEmbeddings):
        self.async_embeddings = async_embeddings

    def embed_query(self, text: str) -> List[float]:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(self.async_embeddings.embed_query(text), loop).result()
        else:
            return loop.run_until_complete(self.async_embeddings.embed_query(text))

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(self.async_embeddings.embed_documents(texts), loop).result()
        else:
            return loop.run_until_complete(self.async_embeddings.embed_documents(texts))

# ✅ ВСЕ ФУНКЦИИ ТЕПЕРЬ АСИНХРОННЫЕ
async def load_documents_async():
    """Асинхронно загружает документы из разных источников."""
    loop = asyncio.get_running_loop()
    def _load():
        docs = []
        for path in DOCUMENTS_PATHS:
            if not os.path.exists(path):
                logging.warning(f"Файл не найден: {path}, пропускаем")
                continue
            if path.endswith(".pdf"):
                loader = PyPDFLoader(path)
            elif path.endswith(".txt"):
                loader = TextLoader(path, encoding="utf-8")
            else:
                logging.warning(f"Неподдерживаемый формат файла: {path}")
                continue
            docs.extend(loader.load())
        return docs
    return await loop.run_in_executor(None, _load)

async def get_vectorstore_async():
    """
    Асинхронно создает или загружает векторную базу данных.
    """
    embeddings = await FridaEmbeddings.create()
    sync_embeddings = SyncFridaEmbeddings(embeddings)

    loop = asyncio.get_running_loop()

    CHROMA_DB_PATH = config.CHROMA_DB_PATH
    if not os.path.exists(CHROMA_DB_PATH):
        logging.info("Создание новой векторной базы ChromaDB (асинхронно)...")
        documents = await load_documents_async()
        if not documents:
            logging.warning("Документы не найдены, создается пустая база знаний")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents) if documents else []
        
        create_task = functools.partial(
            Chroma.from_documents,
            documents=splits,
            embedding=sync_embeddings,
            persist_directory=CHROMA_DB_PATH,
        )
        vectorstore = await loop.run_in_executor(None, create_task)
        logging.info("Векторная база успешно создана и сохранена.")
    else:
        logging.info("Загрузка существующей векторной базы ChromaDB (асинхронно)...")
        load_task = functools.partial(
            Chroma, 
            persist_directory=CHROMA_DB_PATH, 
            embedding_function=sync_embeddings
        )
        vectorstore = await loop.run_in_executor(None, load_task)
    return vectorstore

def read_system_prompt() -> str:
    """Читает системный промпт из файла."""
    try:
        PROMPT_PATH = config.PROMPT_PATH
        with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"Файл системного промпта не найден: {config.PROMPT_PATH}")
        return "Ты — полезный ассистент."

SYSTEM_PROMPT = read_system_prompt() + """--- СПЕЦИАЛЬНЫЕ КОМАНДЫ ---
Если пользователь явно выражает желание записаться на пробный урок, 
начать запись, выбрать время или что-то подобное, 
твой ЕДИНСТВЕННЫЙ ответ должен быть специальной командой: [START_ENROLLMENT].
Если пользователь явно выражает желание отменить существующую запись, пробный 
урок или встречу, ответь только одной командой: [CANCEL_BOOKING]. 
Не пиши ничего, кроме этих команд. Во всех остальных случаях веди диалог как обычно."""

