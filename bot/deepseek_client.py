from __future__ import annotations

import logging
import os
import re
import math
from collections import Counter
import aiohttp

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 4

SYSTEM_PROMPT = (
    "Ты помощник жильцов жилого комплекса. "
    "Тебе будут предоставлены фрагменты документов по работе шлагбаума и бота верификации. "
    "Отвечай СТРОГО на основе этих фрагментов. "
    "Если ответа нет в предоставленных фрагментах — ответь: "
    "'Извините, в документах нет информации по вашему вопросу. Обратитесь к администратору.' "
    "Не используй общие знания за пределами предоставленных документов. "
    "Отвечай на русском языке, кратко и по делу."
)


# ── File reading ──────────────────────────────────────────────────

def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _read_pdf(path: str) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        logger.warning("pypdf not installed, skipping %s", path)
        return ""
    except Exception:
        logger.exception("Failed to read PDF %s", path)
        return ""

def _read_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        logger.warning("python-docx not installed, skipping %s", path)
        return ""
    except Exception:
        logger.exception("Failed to read DOCX %s", path)
        return ""

def _read_file(path: str) -> str:
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("txt", "md"):
        return _read_txt(path)
    elif ext == "pdf":
        return _read_pdf(path)
    elif ext == "docx":
        return _read_docx(path)
    return ""


# ── Chunking ──────────────────────────────────────────────────────

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


# ── TF-IDF search (no external deps) ─────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z0-9]+", text.lower())

def _tfidf_search(query: str, chunks: list[str], top_k: int = TOP_K) -> list[str]:
    if not chunks:
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return chunks[:top_k]

    # TF for each chunk
    chunk_tokens = [_tokenize(c) for c in chunks]

    # IDF
    n = len(chunks)
    df: Counter = Counter()
    for tokens in chunk_tokens:
        for t in set(tokens):
            df[t] += 1
    idf = {t: math.log((n + 1) / (df[t] + 1)) for t in df}

    # Score each chunk
    scores = []
    for i, tokens in enumerate(chunk_tokens):
        tf = Counter(tokens)
        total = len(tokens) or 1
        score = sum((tf[t] / total) * idf.get(t, 0) for t in query_tokens if t in tf)
        scores.append((score, i))

    scores.sort(reverse=True)
    top = [chunks[i] for score, i in scores[:top_k] if score > 0]
    return top if top else []


# ── Knowledge store ───────────────────────────────────────────────

class KnowledgeStore:
    def __init__(self, topic: str):
        self.topic = topic
        self._chunks: list[str] = []

    def load(self, folder: str) -> int:
        if not os.path.isdir(folder):
            logger.warning("Knowledge folder not found: %s", folder)
            return 0
        chunks = []
        for filename in sorted(os.listdir(folder)):
            path = os.path.join(folder, filename)
            if not os.path.isfile(path):
                continue
            text = _read_file(path)
            if not text.strip():
                continue
            file_chunks = _chunk_text(text)
            chunks.extend(file_chunks)
            logger.info("Loaded %s: %d chunks", filename, len(file_chunks))
        self._chunks = chunks
        logger.info("Topic '%s': %d total chunks", self.topic, len(chunks))
        return len(chunks)

    def search(self, query: str) -> list[str]:
        return _tfidf_search(query, self._chunks, TOP_K)


# ── DeepSeek client ───────────────────────────────────────────────

class DeepSeekClient:
    def __init__(self, api_key: str, knowledge_base_dir: str, rag_persist_dir: str = ""):
        self.api_key = api_key
        self.knowledge_base_dir = knowledge_base_dir
        self._stores: dict[str, KnowledgeStore] = {}
        self._store = KnowledgeStore("general")

    def reload_knowledge(self) -> None:
        self._stores.clear()
        all_chunks = []
        for topic in ("barrier", "bot"):
            folder = os.path.join(self.knowledge_base_dir, topic)
            if os.path.isdir(folder):
                store = KnowledgeStore(topic)
                store.load(folder)
                self._stores[topic] = store
                all_chunks.extend(store._chunks)
        self._store._chunks = all_chunks
        logger.info("Total chunks loaded: %d", len(all_chunks))

    async def ask(self, topic: str, question: str) -> str:
        store = self._stores.get(topic) if topic in ("barrier", "bot") else None
        chunks = store.search(question) if store else self._store.search(question)
        if not chunks:
            return "Извините, документы ещё не загружены. Обратитесь к администратору."

        context = "\n\n---\n\n".join(chunks)
        system = SYSTEM_PROMPT
        user_message = f"Фрагменты документов:\n\n{context}\n\nВопрос: {question}"

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DEEPSEEK_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error("DeepSeek API error %s: %s", resp.status, text[:300])
                        return "Сервис временно недоступен. Попробуйте позже."
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception:
            logger.exception("DeepSeek request failed")
            return "Сервис временно недоступен. Попробуйте позже."
