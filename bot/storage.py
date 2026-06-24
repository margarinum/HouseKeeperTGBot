from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_in_group INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    display_name TEXT,
                    house TEXT,
                    entrance TEXT,
                    floor TEXT,
                    apartment TEXT,
                    verified_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    username TEXT,
                    full_name TEXT,
                    added_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verification_attempts (
                    user_id INTEGER PRIMARY KEY,
                    attempts_left INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS apartment_limits (
                    house TEXT NOT NULL,
                    apartment TEXT NOT NULL,
                    max_users INTEGER NOT NULL DEFAULT 10,
                    PRIMARY KEY (house, apartment)
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS polls (
                    poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    closes_at TEXT,
                    is_closed INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS poll_options (
                    option_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_id INTEGER NOT NULL REFERENCES polls(poll_id),
                    option_text TEXT NOT NULL,
                    display_order INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS poll_votes (
                    poll_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    option_id INTEGER NOT NULL,
                    voted_at TEXT NOT NULL,
                    PRIMARY KEY (poll_id, user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    added_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS faq (
                    key TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    async def seed_admins(self, admin_ids: list[int]) -> None:
        with self._connect() as conn:
            for user_id in admin_ids:
                conn.execute("INSERT OR IGNORE INTO admins(user_id, added_by, added_at) VALUES (?, ?, ?)", (user_id, user_id, now_iso()))
            conn.commit()

    async def touch_user(self, user_id: int, username: str | None, full_name: str | None) -> None:
        ts = now_iso()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO user_profiles(user_id, username, full_name, first_seen_at, last_seen_at, is_in_group)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    last_seen_at=excluded.last_seen_at,
                    is_in_group=1
            """, (user_id, username or "", full_name or "", ts, ts))
            conn.commit()

    async def mark_users_absent_except(self, present_ids: Iterable[int]) -> None:
        present_ids = list(present_ids)
        with self._connect() as conn:
            conn.execute("UPDATE user_profiles SET is_in_group=0")
            if present_ids:
                placeholders = ",".join("?" for _ in present_ids)
                conn.execute(f"UPDATE user_profiles SET is_in_group=1 WHERE user_id IN ({placeholders})", present_ids)
            conn.commit()

    async def save_verification(self, user_id: int, username: str | None, full_name: str | None, display_name: str, house: str, entrance: str, floor: str, apartment: str) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO verifications(user_id, username, full_name, display_name, house, entrance, floor, apartment, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    display_name=excluded.display_name,
                    house=excluded.house,
                    entrance=excluded.entrance,
                    floor=excluded.floor,
                    apartment=excluded.apartment,
                    verified_at=excluded.verified_at
            """, (user_id, username or "", full_name or "", display_name, house, entrance, floor, apartment, now_iso()))
            conn.execute("INSERT OR REPLACE INTO verification_attempts(user_id, attempts_left, updated_at) VALUES (?, ?, ?)", (user_id, 3, now_iso()))
            conn.commit()

    async def get_verification(self, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM verifications WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    async def delete_verification(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM verifications WHERE user_id=?", (user_id,))
            conn.commit()

    async def list_verifications_for_user_ids(self, user_ids: set[int]) -> list[dict]:
        if not user_ids:
            return []
        ids = list(user_ids)
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM verifications WHERE user_id IN ({placeholders})", ids).fetchall()
            return [dict(row) for row in rows]

    async def get_unverified_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT p.*
                FROM user_profiles p
                LEFT JOIN verifications v ON v.user_id = p.user_id
                WHERE p.is_in_group=1 AND v.user_id IS NULL
                ORDER BY p.first_seen_at ASC
            """).fetchall()
            return [dict(row) for row in rows]

    async def is_admin(self, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
            return row is not None

    async def add_admin(self, user_id: int, added_by: int, username: str = "", full_name: str = "") -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO admins(user_id, added_by, username, full_name, added_at) VALUES (?, ?, ?, ?, ?)", (user_id, added_by, username, full_name, now_iso()))
            conn.commit()

    async def remove_admin(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
            conn.commit()

    async def list_admins(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM admins ORDER BY added_at ASC").fetchall()
            return [dict(row) for row in rows]

    async def count_admins(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0])

    async def get_attempts_left(self, user_id: int, default: int = 3) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT attempts_left FROM verification_attempts WHERE user_id=?", (user_id,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO verification_attempts(user_id, attempts_left, updated_at) VALUES (?, ?, ?)", (user_id, default, now_iso()))
                conn.commit()
                return default
            return int(row["attempts_left"])

    async def set_attempts_left(self, user_id: int, attempts_left: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO verification_attempts(user_id, attempts_left, updated_at) VALUES (?, ?, ?)", (user_id, attempts_left, now_iso()))
            conn.commit()

    async def decrement_attempts(self, user_id: int) -> int:
        current = await self.get_attempts_left(user_id)
        new_value = max(0, current - 1)
        await self.set_attempts_left(user_id, new_value)
        return new_value

    async def get_user_profile(self, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    async def set_apartment_limit(self, house: str, apartment: str, max_users: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO apartment_limits(house, apartment, max_users) VALUES (?, ?, ?) "
                "ON CONFLICT(house, apartment) DO UPDATE SET max_users=excluded.max_users",
                (house, apartment, max_users),
            )
            conn.commit()

    async def get_apartment_limit(self, house: str, apartment: str, default: int = 3) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT max_users FROM apartment_limits WHERE house=? AND apartment=?",
                (house, apartment),
            ).fetchone()
            return int(row["max_users"]) if row else default

    async def create_poll(self, question: str, options: list[str], created_by: int, closes_at: str | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO polls(question, created_by, created_at, closes_at) VALUES (?, ?, ?, ?)",
                (question, created_by, now_iso(), closes_at),
            )
            poll_id = cur.lastrowid
            for i, text in enumerate(options):
                conn.execute(
                    "INSERT INTO poll_options(poll_id, option_text, display_order) VALUES (?, ?, ?)",
                    (poll_id, text, i),
                )
            conn.commit()
            return poll_id

    async def get_poll(self, poll_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM polls WHERE poll_id=?", (poll_id,)).fetchone()
            return dict(row) if row else None

    async def get_poll_options(self, poll_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM poll_options WHERE poll_id=? ORDER BY display_order", (poll_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    async def get_active_polls(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM polls WHERE is_closed=0 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    async def save_vote(self, poll_id: int, user_id: int, option_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO poll_votes(poll_id, user_id, option_id, voted_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(poll_id, user_id) DO UPDATE SET option_id=excluded.option_id, voted_at=excluded.voted_at",
                (poll_id, user_id, option_id, now_iso()),
            )
            conn.commit()

    async def get_user_vote(self, poll_id: int, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM poll_votes WHERE poll_id=? AND user_id=?", (poll_id, user_id)
            ).fetchone()
            return dict(row) if row else None

    async def get_poll_results(self, poll_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT o.option_id, o.option_text, COUNT(v.user_id) as vote_count
                FROM poll_options o
                LEFT JOIN poll_votes v ON v.option_id = o.option_id AND v.poll_id = o.poll_id
                WHERE o.poll_id = ?
                GROUP BY o.option_id
                ORDER BY o.display_order
            """, (poll_id,)).fetchall()
            return [dict(r) for r in rows]

    async def close_poll(self, poll_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE polls SET is_closed=1 WHERE poll_id=?", (poll_id,))
            conn.commit()

    async def list_all_verifications(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM verifications ORDER BY verified_at ASC").fetchall()
            return [dict(r) for r in rows]

    async def get_poll_voters(self, poll_id: int) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id FROM poll_votes WHERE poll_id=?", (poll_id,)
            ).fetchall()
            return [r["user_id"] for r in rows]

    # ── Documents ──────────────────────────────────────────────

    async def add_document(self, name: str, filename: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents(name, filename, added_at) VALUES (?, ?, ?)",
                (name, filename, now_iso()),
            )
            conn.commit()
            return cur.lastrowid

    async def list_documents(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY added_at ASC").fetchall()
            return [dict(r) for r in rows]

    async def delete_document(self, doc_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
            conn.commit()

    # ── FAQ ────────────────────────────────────────────────────

    async def set_faq_items(self, key: str, items: list[dict]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO faq(key, text, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at",
                (key, json.dumps(items, ensure_ascii=False), now_iso()),
            )
            conn.commit()

    async def get_faq_items(self, key: str) -> list[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT text FROM faq WHERE key=?", (key,)).fetchone()
            if not row:
                return []
            raw = row["text"]
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    return items
            except json.JSONDecodeError:
                pass
            return [{"type": "text", "text": raw}]
