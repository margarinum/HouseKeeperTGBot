from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass(slots=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    group_id: int
    gas_web_app_url: str
    gas_shared_secret: str
    admin_ids: list[int]
    db_path: str
    log_level: str
    telethon_session: str
    announcement_thread_id: int | None
    deepseek_api_key: str

def req(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing env variable: {name}')
    return value

def parse_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(',') if x.strip()]

def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        bot_token=req('BOT_TOKEN'),
        api_id=int(req('API_ID')),
        api_hash=req('API_HASH'),
        group_id=int(req('GROUP_ID')),
        gas_web_app_url=req('GAS_WEB_APP_URL'),
        gas_shared_secret=req('GAS_SHARED_SECRET'),
        admin_ids=parse_ids(req('ADMIN_IDS')),
        db_path=os.getenv('DB_PATH', 'house_bot.db').strip() or 'house_bot.db',
        log_level=os.getenv('LOG_LEVEL', 'INFO').strip() or 'INFO',
        telethon_session=os.getenv('TELETHON_SESSION', 'house_bot_session').strip() or 'house_bot_session',
        announcement_thread_id=int(os.getenv('ANNOUNCEMENT_THREAD_ID', '0').strip()) or None,
        deepseek_api_key=os.getenv('DEEPSEEK_API_KEY', '').strip(),
    )
