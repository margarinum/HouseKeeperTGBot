from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler

_prompt_logger: logging.Logger | None = None


def setup_prompt_logger(log_dir: str) -> logging.Logger:
    """Dedicated daily-rotating log for user AI prompts (not mixed with house_bot.log)."""
    global _prompt_logger
    os.makedirs(log_dir, exist_ok=True)
    log_fmt = logging.Formatter("%(asctime)s | %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "user_prompts.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(log_fmt)

    logger = logging.getLogger("house_bot.prompts")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.propagate = False

    _prompt_logger = logger
    return logger


def _one_line(text: str) -> str:
    return text.replace("\n", " ").strip()


def log_user_ai_exchange(
    *,
    user_id: int,
    username: str | None,
    full_name: str,
    topic: str,
    question: str,
    answer: str,
) -> None:
    if _prompt_logger is None:
        return
    username_label = f"@{username}" if username else "-"
    name = (full_name or "").strip() or str(user_id)
    _prompt_logger.info(
        "user_id=%s | %s | %s | topic=%s | Q: %s | A: %s",
        user_id,
        username_label,
        name,
        topic,
        _one_line(question),
        _one_line(answer),
    )
