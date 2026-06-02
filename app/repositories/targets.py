from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from app.db import get_db
from app.utils.jsonx import dumps, loads, row_to_dict


@dataclass
class Target:
    id: int
    owner_user_id: int
    target_input: str
    target_type: str | None
    target_peer: dict[str, Any]
    target_title: str | None
    target_username: str | None
    status: str
    last_error: str | None


class TargetRepo:
    async def create_pending(self, owner_user_id: int, target_input: str) -> Target:
        async with get_db() as db:
            cur = await db.execute(
                "INSERT INTO targets (owner_user_id, target_input, status) VALUES (?, ?, 'pending')",
                (owner_user_id, target_input),
            )
            await db.commit()
            return await self.get(cur.lastrowid)

    async def mark_checked(
        self,
        target_id: int,
        *,
        status: str,
        target_type: str | None = None,
        target_peer: dict[str, Any] | None = None,
        target_title: str | None = None,
        target_username: str | None = None,
        last_error: str | None = None,
    ) -> Target:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE targets SET
                    status=?, target_type=?, target_peer_json=?, target_title=?, target_username=?,
                    last_error=?, last_check_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, target_type, dumps(target_peer or {}), target_title, target_username, last_error, target_id),
            )
            await db.commit()
        return await self.get(target_id)

    async def list_by_owner(self, owner_user_id: int) -> list[Target]:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM targets WHERE owner_user_id=? ORDER BY id DESC", (owner_user_id,))
            return [self._map(r) for r in await cur.fetchall()]

    async def update_input(self, target_id: int, owner_user_id: int, target_input: str) -> Target | None:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE targets SET
                    target_input=?, status='pending', target_type=NULL, target_peer_json='{}',
                    target_title=NULL, target_username=NULL, last_error=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND owner_user_id=?
                """,
                (target_input, target_id, owner_user_id),
            )
            await db.commit()
        return await self.get(target_id)

    async def delete(self, target_id: int, owner_user_id: int) -> bool:
        async with get_db() as db:
            cur = await db.execute("DELETE FROM targets WHERE id=? AND owner_user_id=?", (target_id, owner_user_id))
            await db.commit()
            return cur.rowcount > 0

    async def get(self, target_id: int) -> Target | None:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM targets WHERE id=?", (target_id,))
            return self._map(await cur.fetchone())

    def _map(self, row: Any) -> Target | None:
        if not row:
            return None
        d = row_to_dict(row)
        return Target(
            id=d['id'],
            owner_user_id=d['owner_user_id'],
            target_input=d['target_input'],
            target_type=d.get('target_type'),
            target_peer=loads(d.get('target_peer_json'), {}),
            target_title=d.get('target_title'),
            target_username=d.get('target_username'),
            status=d['status'],
            last_error=d.get('last_error'),
        )
