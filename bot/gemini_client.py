from __future__ import annotations

import logging
import os
import aiohttp

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

SYSTEM_PROMPTS = {
    "barrier": (
        "Ты помощник по вопросам работы шлагбаума жилого комплекса. "
        "Отвечай ТОЛЬКО на вопросы связанные со шлагбаумом, основываясь исключительно на предоставленных документах. "
        "Если вопрос не по теме шлагбаума или ответа нет в документах — вежливо сообщи что не можешь помочь "
        "и предложи обратиться к администратору. Отвечай на русском языке, кратко и по делу."
    ),
    "bot": (
        "Ты помощник по вопросам работы бота верификации жильцов. "
        "Отвечай ТОЛЬКО на вопросы связанные с работой бота, основываясь исключительно на предоставленных документах. "
        "Если вопрос не по теме бота или ответа нет в документах — вежливо сообщи что не можешь помочь "
        "и предложи обратиться к администратору. Отвечай на русском языке, кратко и по делу."
    ),
}


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


def load_knowledge(folder: str) -> str:
    """Read all txt/pdf/docx files from folder and return combined text."""
    if not os.path.isdir(folder):
        logger.warning("Knowledge folder not found: %s", folder)
        return ""

    parts = []
    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue
        ext = filename.lower().rsplit(".", 1)[-1]
        text = ""
        if ext == "txt" or ext == "md":
            text = _read_txt(path)
        elif ext == "pdf":
            text = _read_pdf(path)
        elif ext == "docx":
            text = _read_docx(path)
        else:
            continue
        if text.strip():
            parts.append(f"=== {filename} ===\n{text.strip()}")
            logger.info("Loaded knowledge file: %s (%d chars)", filename, len(text))

    combined = "\n\n".join(parts)
    logger.info("Total knowledge loaded from %s: %d chars", folder, len(combined))
    return combined


class GeminiClient:
    def __init__(self, api_key: str, knowledge_base_dir: str):
        self.api_key = api_key
        self.knowledge_base_dir = knowledge_base_dir
        self._knowledge: dict[str, str] = {}

    def reload_knowledge(self) -> None:
        for topic in ("barrier", "bot"):
            folder = os.path.join(self.knowledge_base_dir, topic)
            self._knowledge[topic] = load_knowledge(folder)

    def _build_prompt(self, topic: str, question: str) -> str:
        knowledge = self._knowledge.get(topic, "")
        if knowledge:
            return (
                f"Документы для ответа:\n\n{knowledge}\n\n"
                f"Вопрос пользователя: {question}"
            )
        return f"Вопрос пользователя: {question}"

    async def ask(self, topic: str, question: str) -> str:
        system = SYSTEM_PROMPTS.get(topic, "")
        prompt = self._build_prompt(topic, question)

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            },
        }

        url = f"{GEMINI_API_URL}?key={self.api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error("Gemini API error %s: %s", resp.status, text[:300])
                        return "Сервис временно недоступен. Попробуйте позже."
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return "Не удалось получить ответ. Попробуйте переформулировать вопрос."
                    return candidates[0]["content"]["parts"][0]["text"].strip()
        except Exception:
            logger.exception("Gemini request failed")
            return "Сервис временно недоступен. Попробуйте позже."
