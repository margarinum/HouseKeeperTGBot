from __future__ import annotations

import json
import logging
import ssl
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

BARRIER_API_URL = "https://lk.amvideo-msk.ru/api/api4.php"

BARRIERS: dict[str, dict[str, int | str]] = {
    "3k4_north": {"label": "3К4 СЕВЕР", "id_shlag": 3146, "relay": 0},
    "3k4_south": {"label": "3К4 ЮГ", "id_shlag": 3147, "relay": 0},
    "5k3": {"label": "5К3", "id_shlag": 3148, "relay": 0},
}

# Ключи payload, которые нужно маскировать в логах
SENSITIVE_KEYS = {"password"}


class BarrierClientError(Exception):
    pass


class ChangeDeviceRequired(Exception):
    """Сервер требует подтверждение устройства PIN-кодом из SMS."""


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


def _mask_payload(payload: dict) -> dict:
    """Возвращает копию payload с замаскированными чувствительными полями для логов."""
    masked = dict(payload)
    for key in SENSITIVE_KEYS:
        if key in masked:
            masked[key] = "***"
    return masked


class BarrierClient:
    def __init__(self, api_url: str, login: str, password: str, config_path: str):
        self.api_url = api_url
        self.login_phone = login
        self.password = password
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE
        logger.info(
            "BarrierClient инициализирован: url=%s, login=%s, config=%s, device_key=%s",
            self.api_url,
            self.login_phone,
            self.config_path,
            self.device_key,
        )

    # ── config.json (device_key / sid) ──────────────────────────

    def _load_config(self) -> dict:
        """Загружает config.json. Если файла нет — генерирует device_key."""
        if self.config_path.exists():
            with self.config_path.open(encoding="utf-8") as f:
                config = json.load(f)
            logger.info("config.json загружен: %s", self.config_path.resolve())
        else:
            config = {}
            logger.info("config.json не найден, будет создан: %s", self.config_path.resolve())

        changed = False
        if not config.get("device_key"):
            config["device_key"] = str(uuid.uuid4())
            changed = True
            logger.info("Сгенерирован новый device_key: %s", config["device_key"])
        if "sid" not in config:
            config["sid"] = None
            changed = True

        if changed:
            self._config = config
            self._save_config()
        return config

    def _save_config(self, config: dict | None = None) -> None:
        if config is not None:
            self._config = config
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)
        logger.info("config.json сохранён (device_key=%s, sid=%s)", self.device_key, self._config.get("sid"))

    @property
    def device_key(self) -> str:
        return self._config["device_key"]

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.login_phone and self.password)

    # ── HTTP ────────────────────────────────────────────────────

    async def _post(self, payload: dict) -> dict:
        logger.info("→ POST %s payload=%s", self.api_url, _mask_payload(payload))
        connector = aiohttp.TCPConnector(ssl=self._ssl_context)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(self.api_url, data=payload, timeout=timeout) as response:
                    text = await response.text()
                    logger.info("← HTTP %s body=%s", response.status, text[:500])
                    if response.status >= 400:
                        raise BarrierClientError(f"HTTP {response.status}: {text[:300]}")
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise BarrierClientError(f"некорректный ответ сервера: {text[:300]}") from exc
        except BarrierClientError:
            raise
        except Exception as exc:
            logger.warning("Ошибка запроса к API шлагбаумов: %s", exc)
            raise BarrierClientError(str(exc)) from exc

        if not isinstance(data, dict):
            raise BarrierClientError(f"неожиданный ответ сервера: {text[:300]}")
        return data

    # ── API ─────────────────────────────────────────────────────

    async def request_sms_pin(self) -> None:
        """Просит сервер отправить SMS с PIN для подтверждения устройства."""
        logger.info("Запрашиваем SMS с PIN (type=pin)")
        await self._post({
            "type": "pin",
            "login": self.login_phone,
            "pin_type": "login",
            "sms": "0",
        })

    async def fetch_sid(self, pin: str | None = None) -> str:
        """Логинится и возвращает свежий sid. Сохраняет его в config.json.

        Если сервер требует подтверждения устройства — при первом логине (без PIN)
        дополнительно инициирует отправку SMS и бросает ChangeDeviceRequired.
        """
        logger.info("Логин в API шлагбаумов (pin=%s)", "да" if pin else "нет")
        payload = {
            "type": "login",
            "login": self.login_phone,
            "password": self.password,
            "device_key": self.device_key,
        }
        if pin:
            payload["pin"] = pin

        data = await self._post(payload)

        if data.get("change_device"):
            logger.info("Сервер запросил подтверждение устройства (change_device=true)")
            # SMS приходит только после отдельного запроса type=pin.
            # Инициируем его только при первом логине (когда PIN ещё не вводили).
            if not pin:
                await self.request_sms_pin()
            raise ChangeDeviceRequired()

        sid = data.get("sid")
        if not sid:
            response = BarrierApiResponse.from_data(data)
            detail = response.message or json.dumps(data, ensure_ascii=False)
            logger.warning("Логин не вернул sid: %s", detail)
            raise BarrierClientError(f"не удалось получить sid: {detail}")

        logger.info("Получен sid (длина %d)", len(str(sid)))
        self._config["sid"] = str(sid)
        self._save_config()
        return str(sid)

    async def open_barrier(self, barrier_key: str, pin: str | None = None) -> BarrierApiResponse:
        barrier = BARRIERS.get(barrier_key)
        if not barrier:
            raise BarrierClientError(f"неизвестный шлагбаум: {barrier_key}")

        logger.info(
            "Открытие шлагбаума '%s' (id_shlag=%s, relay=%s, pin=%s)",
            barrier["label"],
            barrier["id_shlag"],
            barrier["relay"],
            "да" if pin else "нет",
        )

        # Перед каждым открытием логинимся и получаем свежий sid
        sid = await self.fetch_sid(pin)
        data = await self._post({
            "type": "open",
            "id_shlag": str(barrier["id_shlag"]),
            "relay": str(barrier["relay"]),
            "sid": sid,
        })
        result = BarrierApiResponse.from_data(data)
        logger.info(
            "Результат открытия '%s': ok=%s, message=%s",
            barrier["label"],
            result.ok,
            result.message,
        )
        return result
