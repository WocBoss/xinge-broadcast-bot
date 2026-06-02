from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db import get_db
from app.utils.jsonx import row_to_dict


@dataclass
class AccountSession:
    id: int
    owner_user_id: int
    provider: str
    status: str
    phone: str | None
    display_name: str | None
    session_encrypted: str | None
    last_error: str | None


class AccountSessionRepo:
    async def get_by_owner(self, owner_user_id: int) -> AccountSession | None:
        async with get_db() as db:
            cur = await db.execute('SELECT * FROM account_sessions WHERE owner_user_id=?', (owner_user_id,))
            return self._map(await cur.fetchone())

    async def upsert_status(
        self,
        owner_user_id: int,
        *,
        status: str,
        phone: str | None = None,
        display_name: str | None = None,
        session_encrypted: str | None = None,
        last_error: str | None = None,
    ) -> AccountSession:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO account_sessions (
                    owner_user_id, provider, status, phone, display_name, session_encrypted, last_error
                ) VALUES (?, 'mtproto', ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    status=excluded.status,
                    phone=COALESCE(excluded.phone, account_sessions.phone),
                    display_name=COALESCE(excluded.display_name, account_sessions.display_name),
                    session_encrypted=COALESCE(excluded.session_encrypted, account_sessions.session_encrypted),
                    last_error=excluded.last_error,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (owner_user_id, status, phone, display_name, session_encrypted, last_error),
            )
            await db.commit()
        return await self.get_by_owner(owner_user_id)

    async def delete_by_owner(self, owner_user_id: int) -> bool:
        async with get_db() as db:
            cur = await db.execute('DELETE FROM account_sessions WHERE owner_user_id=?', (owner_user_id,))
            await db.commit()
            return cur.rowcount > 0

    def _map(self, row: Any) -> AccountSession | None:
        if not row:
            return None
        d = row_to_dict(row)
        return AccountSession(
            id=d['id'],
            owner_user_id=d['owner_user_id'],
            provider=d['provider'],
            status=d['status'],
            phone=d.get('phone'),
            display_name=d.get('display_name'),
            session_encrypted=d.get('session_encrypted'),
            last_error=d.get('last_error'),
        )
