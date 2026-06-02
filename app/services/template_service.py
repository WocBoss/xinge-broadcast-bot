from __future__ import annotations

from typing import Any
from telegram import Message
from app.repositories.templates import TemplateRepo, MessageTemplate


class TemplateService:
    def __init__(self):
        self.repo = TemplateRepo()

    async def save_from_message(self, owner_user_id: int, message: Message) -> MessageTemplate:
        payload = message.to_dict()
        payload['message_type'] = self._detect_message_type(payload)
        return await self.repo.create_from_message(owner_user_id, payload)

    async def list_recent(self, owner_user_id: int, limit: int = 10) -> list[MessageTemplate]:
        return await self.repo.list_by_owner(owner_user_id, limit)

    async def update_text(self, owner_user_id: int, template_id: int, text: str) -> MessageTemplate:
        template = await self.repo.update_text(template_id, owner_user_id, text)
        if not template:
            raise ValueError('模板不存在')
        return template

    async def delete(self, owner_user_id: int, template_id: int) -> None:
        deleted = await self.repo.delete(template_id, owner_user_id)
        if not deleted:
            raise ValueError('模板不存在')

    def _detect_message_type(self, payload: dict[str, Any]) -> str:
        for key in ('photo', 'video', 'animation', 'document', 'sticker', 'audio', 'voice', 'video_note'):
            if payload.get(key):
                return key
        return 'text' if payload.get('text') else 'message'
