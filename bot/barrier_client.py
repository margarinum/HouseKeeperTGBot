from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

BARRIER_API_URL = "https://lk.amvideo-msk.ru/api/api4.php"

BARRIERS: dict[str, dict[str, int | str]] = {
    "5k2": {"label": "5к2", "id_shlag": 3146, "relay": 0},
    "3k4_north": {"label": "3к4 (север)", "id_shlag": 3147, "relay": 0},
    "3k4_south": {"label": "3к4 (юг)", "id_shlag": 3148, "relay": 0},
}


class BarrierClientError(Exception):
    pass


@dataclass(slots=True)
class BarrierApiResponse:
    ok: bool
    message: str
    raw: dict

    @classmethod
    def from_data(cls, data: dict) -> BarrierApiResponse:
        result = data.get("result")
        ok = result is True or result == 1 or result == "1"
        message = str(data.get("str") or data.get("message") or "").strip()
        return cls(ok=ok, message=message, raw=data)


class BarrierClient:
    def __init__(self, api_url: str, login: str, password: str, device_key: str):
        self.api_url = api_url
        self.login_phone = login
        self.password = password
        self.device_key = device_key
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.login_phone and self.password and self.device_key)

    async def _post(self, payload: dict) -> dict:
        connector = aiohttp.TCPConnector(ssl=self._ssl_context)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(self.api_url, data=payload, timeout=timeout) as response:
                    text = await response.text()
                    if response.status >= 400:
                        raise BarrierClientError(f"HTTP {response.status}: {text[:300]}")
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise BarrierClientError(f"Некорректный ответ сервера: {text[:300]}") from exc
        except BarrierClientError:
            raise
        except Exception as exc:
            raise BarrierClientError(str(exc)) from exc

        if not isinstance(data, dict):
            raise BarrierClientError(f"Неожиданный ответ сервера: {text[:300]}")
        return data

    async def fetch_sid(self) -> str:
        data = await self._post({
            "type": "login",
            "login": self.login_phone,
            "password": self.password,
            "device_key": self.device_key,
        })
        response = BarrierApiResponse.from_data(data)
        sid = data.get("sid")
        if not sid:
            detail = response.message or json.dumps(data, ensure_ascii=False)
            raise BarrierClientError(f"Не удалось получить sid: {detail}")
        return str(sid)

    async def open_barrier(self, barrier_key: str) -> BarrierApiResponse:
        barrier = BARRIERS.get(barrier_key)
        if not barrier:
            raise BarrierClientError(f"Неизвестный шлагбаум: {barrier_key}")

        sid = await self.fetch_sid()
        data = await self._post({
            "type": "open",
            "id_shlag": str(barrier["id_shlag"]),
            "relay": str(barrier["relay"]),
            "sid": sid,
        })
        return BarrierApiResponse.from_data(data)
