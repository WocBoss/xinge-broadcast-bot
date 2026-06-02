from __future__ import annotations

from typing import Any

from telegram import Message

from app.repositories.templates import MessageTemplate, TemplateRepo


class TemplateService:
    def __init__(self):
        self.repo = TemplateRepo()

    async def save_from_message(self, owner_user_id: int, message: Message) -> MessageTemplate:
        payload = self._message_payload(message)
        payload['message_type'] = self._detect_message_type(payload)
        return await self.repo.create_from_message(owner_user_id, payload)

    async def list_recent(self, owner_user_id: int, limit: int = 10) -> list[MessageTemplate]:
        return await self.repo.list_by_owner(owner_user_id, limit)

    async def update_from_message(self, owner_user_id: int, template_id: int, message: Message) -> MessageTemplate:
        payload = self._message_payload(message)
        payload['message_type'] = self._detect_message_type(payload)
        template = await self.repo.update_from_message(template_id, owner_user_id, payload)
        if not template:
            raise ValueError('模板不存在')
        return template

    async def update_text(self, owner_user_id: int, template_id: int, text: str) -> MessageTemplate:
        payload = {'message_type': 'text', 'text': text, 'entities': []}
        template = await self.repo.update_from_message(template_id, owner_user_id, payload)
        if not template:
            raise ValueError('模板不存在')
        return template

    async def delete(self, owner_user_id: int, template_id: int) -> None:
        deleted = await self.repo.delete(template_id, owner_user_id)
        if not deleted:
            raise ValueError('模板不存在')

    def _message_payload(self, message: Message) -> dict[str, Any]:
        payload = message.to_dict()

        # python-telegram-bot's Message.to_dict() is not a stable enough source
        # for formatted text. Keep entities explicitly so bold/links/spoilers and
        # custom emoji survive template save/edit and later MTProto sending.
        if message.text is not None:
            payload['text'] = message.text
            payload['entities'] = self._serialize_entities(message.entities)
        if message.caption is not None:
            payload['caption'] = message.caption
            payload['caption_entities'] = self._serialize_entities(message.caption_entities)

        if message.reply_markup:
            payload['reply_markup'] = message.reply_markup.to_dict()
        return payload

    def _serialize_entities(self, entities: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for entity in entities or []:
            data = entity.to_dict() if hasattr(entity, 'to_dict') else dict(entity)
            entity_type = data.get('type')
            if hasattr(entity_type, 'value'):
                data['type'] = entity_type.value
            custom_emoji_id = getattr(entity, 'custom_emoji_id', None) or data.get('custom_emoji_id')
            if custom_emoji_id:
                data['custom_emoji_id'] = str(custom_emoji_id)
            user = getattr(entity, 'user', None)
            if user and 'user' not in data:
                data['user'] = user.to_dict() if hasattr(user, 'to_dict') else user
            result.append(data)
        return result

    def _detect_message_type(self, payload: dict[str, Any]) -> str:
        for key in ('photo', 'video', 'animation', 'document', 'sticker', 'audio', 'voice', 'video_note'):
            if payload.get(key):
                return key
        return 'text' if payload.get('text') else 'message'
