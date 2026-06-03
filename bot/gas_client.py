from __future__ import annotations

import aiohttp


class GasClientError(Exception):
    pass


class GasClient:
    def __init__(self, web_app_url: str, secret: str):
        self.web_app_url = web_app_url
        self.secret = secret
        self._rows_cache: list[dict] | None = None

    async def _get_rows(self) -> list[dict]:
        """Load all table rows once and cache for the lifetime of the process."""
        if self._rows_cache is None:
            data = await self._post({"action": "get_all_rows"})
            self._rows_cache = data.get("rows") or []
        return self._rows_cache

    def invalidate_cache(self) -> None:
        self._rows_cache = None

    async def _post(self, payload: dict) -> dict:
        payload = dict(payload)
        payload["secret"] = self.secret
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=60, connect=15)
                async with session.post(self.web_app_url, json=payload, timeout=timeout) as response:
                    text = await response.text()
                    if response.status >= 400:
                        raise GasClientError(f"HTTP {response.status}: {text[:300]}")
                    try:
                        data = await response.json(content_type=None)
                    except Exception as exc:
                        raise GasClientError(f"Invalid JSON from Apps Script: {text[:300]}") from exc
        except GasClientError:
            raise
        except Exception as exc:
            raise GasClientError(str(exc)) from exc

        if data.get("status") != "ok":
            raise GasClientError(data.get("message", "Unknown Apps Script error"))
        return data

    async def resolve_house(self, house_input: str) -> str | None:
        """Возвращает номер дома из таблицы (как в Sheets) или None."""
        text = (house_input or "").strip()
        if not text:
            return None
        rows = await self._get_rows()
        for row in rows:
            if row["house"].lower() == text.lower():
                return row["house"]
        return None

    async def apartment_exists_for_house(self, house: str, apartment: str) -> bool:
        rows = await self._get_rows()
        h = house.strip().lower()
        a = str(apartment).strip()
        return any(r["house"].lower() == h and r["apartment"] == a for r in rows)

    async def check_house(self, house: str) -> bool:
        rows = await self._get_rows()
        h = house.strip().lower()
        return any(r["house"].lower() == h for r in rows)

    async def check_entrance(self, house: str, entrance: str) -> bool:
        rows = await self._get_rows()
        h, e = house.strip().lower(), str(entrance).strip()
        return any(r["house"].lower() == h and r["entrance"] == e for r in rows)

    async def check_floor(self, house: str, entrance: str, floor: str) -> bool:
        rows = await self._get_rows()
        h, e, f = house.strip().lower(), str(entrance).strip(), str(floor).strip()
        return any(r["house"].lower() == h and r["entrance"] == e and r["floor"] == f for r in rows)

    async def check_apartment(self, house: str, entrance: str, floor: str, apartment: str) -> bool:
        rows = await self._get_rows()
        h, e, f, a = house.strip().lower(), str(entrance).strip(), str(floor).strip(), str(apartment).strip()
        return any(r["house"].lower() == h and r["entrance"] == e and r["floor"] == f and r["apartment"] == a for r in rows)

    async def verify_user(self, house: str, entrance: str, floor: str, apartment: str, user_id: int, display_name: str, username: str) -> None:
        await self._post({"action": "verify", "house": house, "entrance": entrance, "floor": floor, "apartment": apartment, "user_id": str(user_id), "display_name": display_name, "username": username or ""})

    async def find_user(self, user_id: int) -> dict | None:
        data = await self._post({"action": "find_user", "user_id": str(user_id)})
        return data.get("user") or None

    async def list_users(self) -> list[dict]:
        data = await self._post({"action": "list_users"})
        return data.get("users") or []

    async def list_paid_users(self) -> list[dict]:
        data = await self._post({"action": "list_paid_users"})
        return data.get("users") or []

    async def remove_user(self, user_id: int) -> bool:
        data = await self._post({"action": "remove", "user_id": str(user_id)})
        return bool(data.get("removed"))
    
    async def set_apartment_limit(self, house: str, apartment: str, max_users: int) -> None:
        await self._post({"action": "set_apartment_limit", "house": house, "apartment": apartment, "max_users": max_users})

    async def get_houses(self) -> list[str]:
        rows = await self._get_rows()
        return sorted({r["house"] for r in rows if r["house"]})
