from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from telethon import helpers
from telethon.tl import types

from app.clients.telegram_bot_api import TelegramBotApiClient
from app.repositories.account_sessions import AccountSession
from app.services.account_session_service import AccountSessionService


class AccountSenderService:
    """Send scheduled messages through the user's logged-in Telegram account.

    The control bot only collects templates and settings. Campaign messages are
    sent through the user's MTProto session.
    """

    MEDIA_TYPES = {'photo', 'video', 'animation', 'document', 'sticker', 'audio', 'voice', 'video_note'}

    def __init__(self):
        self.sessions = AccountSessionService()
        self.bot_api = TelegramBotApiClient()

    async def resolve_target(self, owner_user_id: int, target_input: str) -> dict:
        client = await self.sessions.load_client(owner_user_id)
        try:
            entity = await client.get_entity(target_input)
            peer_id = getattr(entity, 'id', None)
            username = getattr(entity, 'username', None)
            title = getattr(entity, 'title', None) or ' '.join(
                x for x in [getattr(entity, 'first_name', None), getattr(entity, 'last_name', None)] if x
            ) or username or str(peer_id)
            entity_type = entity.__class__.__name__.lower()
            return {
                'peer_id': peer_id,
                'access_hash': getattr(entity, 'access_hash', None),
                'username': username,
                'title': title,
                'entity_type': entity_type,
                'raw': target_input,
            }
        finally:
            await client.disconnect()

    async def send_template(self, *, session: AccountSession, target, template) -> dict:
        if session.status != 'connected':
            raise RuntimeError('Telegram 账号尚未连接')

        client = await self.sessions.load_client(session.owner_user_id)
        try:
            entity_ref = target.target_peer.get('username') or target.target_peer.get('raw') or target.target_input
            if template.message_type == 'text':
                return await self._send_text(client, entity_ref, template)
            if template.message_type in self.MEDIA_TYPES:
                return await self._send_media(client, entity_ref, template)
            raise RuntimeError(f'暂不支持这种消息类型：{template.message_type}')
        finally:
            await client.disconnect()

    async def _send_text(self, client, entity_ref: str, template) -> dict:
        message = template.text or template.caption or ''
        if not message.strip():
            raise RuntimeError('模板内容为空')
        text = helpers.add_surrogate(message)
        sent = await client.send_message(
            entity_ref,
            text,
            formatting_entities=self._to_telethon_entities(template.entities),
            parse_mode=None,
        )
        return {'message_id': getattr(sent, 'id', None)}

    async def _send_media(self, client, entity_ref: str, template) -> dict:
        file_id = self._extract_file_id(template.raw_message, template.message_type)
        if not file_id:
            raise RuntimeError('模板里没有可发送的文件')

        file_info = await self.bot_api.get_file(file_id)
        file_path = file_info.get('file_path')
        if not file_path:
            raise RuntimeError('无法下载模板文件')

        suffix = Path(file_path).suffix or self._default_suffix(template.message_type)
        with tempfile.TemporaryDirectory(prefix='xinge-template-') as tmp_dir:
            local_path = Path(tmp_dir) / f'template-{template.id}{suffix}'
            await self.bot_api.download_file(file_path, local_path)
            caption = helpers.add_surrogate(template.caption) if template.caption else None
            sent = await client.send_file(
                entity_ref,
                str(local_path),
                caption=caption,
                formatting_entities=self._to_telethon_entities(template.caption_entities),
                parse_mode=None,
                voice_note=template.message_type == 'voice',
                video_note=template.message_type == 'video_note',
            )
            return {'message_id': getattr(sent, 'id', None)}

    def _to_telethon_entities(self, entities: list[dict[str, Any]] | None):
        result = []
        for entity in entities or []:
            item = self._to_telethon_entity(entity)
            if item:
                result.append(item)
        return result or None

    def _to_telethon_entity(self, entity: dict[str, Any]):
        entity_type = entity.get('type')
        offset = int(entity.get('offset') or 0)
        length = int(entity.get('length') or 0)
        if length <= 0:
            return None

        if entity_type == 'custom_emoji':
            custom_emoji_id = entity.get('custom_emoji_id')
            if not custom_emoji_id:
                return None
            return types.MessageEntityCustomEmoji(offset=offset, length=length, document_id=int(custom_emoji_id))
        if entity_type == 'bold':
            return types.MessageEntityBold(offset=offset, length=length)
        if entity_type == 'italic':
            return types.MessageEntityItalic(offset=offset, length=length)
        if entity_type == 'underline':
            return types.MessageEntityUnderline(offset=offset, length=length)
        if entity_type == 'strikethrough':
            return types.MessageEntityStrike(offset=offset, length=length)
        if entity_type == 'spoiler':
            return types.MessageEntitySpoiler(offset=offset, length=length)
        if entity_type == 'code':
            return types.MessageEntityCode(offset=offset, length=length)
        if entity_type == 'pre':
            return types.MessageEntityPre(offset=offset, length=length, language=entity.get('language') or '')
        if entity_type == 'text_link':
            url = entity.get('url')
            return types.MessageEntityTextUrl(offset=offset, length=length, url=url) if url else None
        if entity_type == 'url':
            return types.MessageEntityUrl(offset=offset, length=length)
        if entity_type == 'email':
            return types.MessageEntityEmail(offset=offset, length=length)
        if entity_type == 'hashtag':
            return types.MessageEntityHashtag(offset=offset, length=length)
        if entity_type == 'cashtag':
            return types.MessageEntityCashtag(offset=offset, length=length)
        if entity_type == 'bot_command':
            return types.MessageEntityBotCommand(offset=offset, length=length)
        if entity_type == 'mention':
            return types.MessageEntityMention(offset=offset, length=length)
        if entity_type == 'phone_number':
            return types.MessageEntityPhone(offset=offset, length=length)
        return None

    def _extract_file_id(self, raw_message: dict[str, Any], message_type: str) -> str | None:
        value = raw_message.get(message_type)
        if message_type == 'photo' and isinstance(value, list) and value:
            return value[-1].get('file_id')
        if isinstance(value, dict):
            return value.get('file_id')
        return None

    def _default_suffix(self, message_type: str) -> str:
        return {
            'photo': '.jpg',
            'video': '.mp4',
            'animation': '.mp4',
            'sticker': '.webp',
            'audio': '.mp3',
            'voice': '.ogg',
            'video_note': '.mp4',
        }.get(message_type, '.bin')
