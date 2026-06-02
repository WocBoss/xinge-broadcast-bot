from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from app.db import get_db
from app.utils.jsonx import dumps, loads, row_to_dict


@dataclass
class MessageTemplate:
    id: int
    owner_user_id: int
    message_type: str
    raw_message: dict[str, Any]
    text: str | None
    entities: list[dict[str, Any]]
    media: dict[str, Any]
    caption: str | None
    caption_entities: list[dict[str, Any]]
    reply_markup: dict[str, Any]


class TemplateRepo:
    async def create_from_message(self, owner_user_id: int, payload: dict[str, Any]) -> MessageTemplate:
        message_type = payload.get('message_type', 'message')
        async with get_db() as db:
            cur = await db.execute(
                """
                INSERT INTO message_templates (
                    owner_user_id, message_type, raw_message_json, text, entities_json,
                    media_json, caption, caption_entities_json, reply_markup_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_user_id,
                    message_type,
                    dumps(payload),
                    payload.get('text'),
                    dumps(payload.get('entities') or []),
                    dumps(payload.get('media') or {}),
                    payload.get('caption'),
                    dumps(payload.get('caption_entities') or []),
                    dumps(payload.get('reply_markup') or {}),
                ),
            )
            await db.commit()
            return await self.get(cur.lastrowid)

    async def get(self, template_id: int) -> MessageTemplate | None:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM message_templates WHERE id=?", (template_id,))
            return self._map(await cur.fetchone())

    async def list_by_owner(self, owner_user_id: int, limit: int = 10) -> list[MessageTemplate]:
        async with get_db() as db:
            cur = await db.execute(
                "SELECT * FROM message_templates WHERE owner_user_id=? ORDER BY id DESC LIMIT ?",
                (owner_user_id, limit),
            )
            return [self._map(r) for r in await cur.fetchall()]

    async def update_from_message(self, template_id: int, owner_user_id: int, payload: dict[str, Any]) -> MessageTemplate | None:
        message_type = payload.get('message_type', 'message')
        async with get_db() as db:
            cur = await db.execute(
                """
                UPDATE message_templates SET
                    message_type=?, raw_message_json=?, text=?, entities_json=?, media_json=?,
                    caption=?, caption_entities_json=?, reply_markup_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND owner_user_id=?
                """,
                (
                    message_type,
                    dumps(payload),
                    payload.get('text'),
                    dumps(payload.get('entities') or []),
                    dumps(payload.get('media') or {}),
                    payload.get('caption'),
                    dumps(payload.get('caption_entities') or []),
                    dumps(payload.get('reply_markup') or {}),
                    template_id,
                    owner_user_id,
                ),
            )
            await db.commit()
            if cur.rowcount <= 0:
                return None
        return await self.get(template_id)

    async def delete(self, template_id: int, owner_user_id: int) -> bool:
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM message_templates WHERE id=? AND owner_user_id=?",
                (template_id, owner_user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    def _map(self, row: Any) -> MessageTemplate | None:
        if not row:
            return None
        d = row_to_dict(row)
        return MessageTemplate(
            id=d['id'],
            owner_user_id=d['owner_user_id'],
            message_type=d['message_type'],
            raw_message=loads(d.get('raw_message_json'), {}),
            text=d.get('text'),
            entities=loads(d.get('entities_json'), []),
            media=loads(d.get('media_json'), {}),
            caption=d.get('caption'),
            caption_entities=loads(d.get('caption_entities_json'), []),
            reply_markup=loads(d.get('reply_markup_json'), {}),
        )
