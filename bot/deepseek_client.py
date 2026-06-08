from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 4
KEYWORD_BOOST = 2.5

SYSTEM_PROMPT = (
    "Ты помощник жильцов жилого комплекса. "
    "Тебе будут предоставлены фрагменты документов по работе шлагбаума и бота верификации. "
    "Отвечай СТРОГО на основе этих фрагментов. "
    "Если ответа нет в предоставленных фрагментах — ответь: "
    "'Извините, в документах нет информации по вашему вопросу. Обратитесь к администратору.' "
    "Не используй общие знания за пределами предоставленных документов. "
    "Отвечай на русском языке, кратко и по делу."
)


@dataclass
class KnowledgeEntry:
    id: str
    title: str
    topic: str
    keywords: list[str]
    content: str

    def format_chunk(self) -> str:
        return f"[{self.title}]\n{self.content}"

    def search_text(self) -> str:
        keywords = " ".join(self.keywords)
        boosted = " ".join(self.keywords * int(KEYWORD_BOOST))
        return f"{self.title}\n{keywords}\n{boosted}\n{self.content}"


# ── File reading (legacy txt/pdf/docx) ──────────────────────────

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
    if ext == "pdf":
        return _read_pdf(path)
    if ext == "docx":
        return _read_docx(path)
    return ""


def _load_json_knowledge(path: str) -> list[KnowledgeEntry]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entries: list[KnowledgeEntry] = []
    for item in data.get("entries", []):
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        keywords = [str(kw).strip() for kw in item.get("keywords", []) if str(kw).strip()]
        entries.append(
            KnowledgeEntry(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")).strip(),
                topic=str(item.get("topic", "")).strip(),
                keywords=keywords,
                content=content,
            )
        )
    return entries


# ── Chunking (legacy) ───────────────────────────────────────────

def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


# ── TF-IDF search ─────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z0-9]+", text.lower())


def _tfidf_search(query: str, texts: list[str], top_k: int = TOP_K) -> list[int]:
    if not texts:
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return list(range(min(top_k, len(texts))))

    tokenized = [_tokenize(text) for text in texts]
    n = len(texts)
    df: Counter[str] = Counter()
    for tokens in tokenized:
        for token in set(tokens):
            df[token] += 1
    idf = {token: math.log((n + 1) / (count + 1)) for token, count in df.items()}

    scores: list[tuple[float, int]] = []
    for index, tokens in enumerate(tokenized):
        tf = Counter(tokens)
        total = len(tokens) or 1
        score = sum((tf[token] / total) * idf.get(token, 0) for token in query_tokens if token in tf)
        scores.append((score, index))

    scores.sort(reverse=True)
    ranked = [index for score, index in scores[:top_k] if score > 0]
    return ranked if ranked else list(range(min(top_k, len(texts))))


def _search_entries(query: str, entries: list[KnowledgeEntry], top_k: int = TOP_K) -> list[str]:
    texts = [entry.search_text() for entry in entries]
    indices = _tfidf_search(query, texts, top_k)
    return [entries[index].format_chunk() for index in indices]


# ── Knowledge store ───────────────────────────────────────────────

class KnowledgeStore:
    def __init__(self, topic: str):
        self.topic = topic
        self._entries: list[KnowledgeEntry] = []
        self._chunks: list[str] = []

    def load(self, folder: str) -> int:
        if not os.path.isdir(folder):
            logger.warning("Knowledge folder not found: %s", folder)
            return 0

        json_path = os.path.join(folder, "knowledge.json")
        if os.path.isfile(json_path):
            self._entries = _load_json_knowledge(json_path)
            self._chunks = [entry.format_chunk() for entry in self._entries]
            logger.info(
                "Loaded JSON knowledge from %s: %d entries",
                json_path,
                len(self._entries),
            )
            return len(self._entries)

        chunks: list[str] = []
        for filename in sorted(os.listdir(folder)):
            path = os.path.join(folder, filename)
            if not os.path.isfile(path):
                continue
            if filename.lower().endswith(".json"):
                continue
            text = _read_file(path)
            if not text.strip():
                continue
            file_chunks = _chunk_text(text)
            chunks.extend(file_chunks)
            logger.info("Loaded %s: %d chunks", filename, len(file_chunks))

        self._entries = []
        self._chunks = chunks
        logger.info("Topic '%s': %d total chunks", self.topic, len(chunks))
        return len(chunks)

    def search(self, query: str) -> list[str]:
        if self._entries:
            return _search_entries(query, self._entries, TOP_K)
        indices = _tfidf_search(query, self._chunks, TOP_K)
        return [self._chunks[i] for i in indices]


# ── DeepSeek client ───────────────────────────────────────────────

class DeepSeekClient:
    def __init__(self, api_key: str, knowledge_base_dir: str, rag_persist_dir: str = ""):
        self.api_key = api_key
        self.knowledge_base_dir = knowledge_base_dir
        self._stores: dict[str, KnowledgeStore] = {}
        self._store = KnowledgeStore("general")

    def reload_knowledge(self) -> None:
        self._stores.clear()
        all_chunks: list[str] = []
        for topic in ("barrier", "bot"):
            folder = os.path.join(self.knowledge_base_dir, topic)
            if os.path.isdir(folder):
                store = KnowledgeStore(topic)
                store.load(folder)
                self._stores[topic] = store
                all_chunks.extend(store._chunks)
        self._store._chunks = all_chunks
        logger.info("Total chunks loaded: %d", len(all_chunks))

    async def ask(
        self,
        topic: str,
        question: str,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        store = self._stores.get(topic) if topic in ("barrier", "bot") else None
        chunks = store.search(question) if store else self._store.search(question)
        if not chunks:
            return "Извините, документы ещё не загружены. Обратитесь к администратору."

        context = "\n\n---\n\n".join(chunks)
        user_message = f"Фрагменты документов:\n\n{context}\n\nВопрос: {question}"

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for prev_q, prev_a in history or []:
            messages.append({"role": "user", "content": prev_q})
            messages.append({"role": "assistant", "content": prev_a})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "deepseek-chat",
            "messages": messages,
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
