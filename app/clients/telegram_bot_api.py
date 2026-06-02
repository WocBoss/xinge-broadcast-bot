from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class TelegramBotApiClient:
    """Minimal Bot API client for the control bot.

    The control bot is only responsible for UI/webhook/preview messages.
    Account-hosted sending must go through MTProto services, not this client.
    """

    def __init__(self, token: str | None = None):
        self.token = token or settings.bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def request(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.base_url}/{method}", json=payload or {})
            data = response.json()
            if not data.get('ok'):
                raise RuntimeError(f"Telegram Bot API {method} failed: {data.get('description') or data}")
            return data['result']

    async def get_me(self) -> dict[str, Any]:
        return await self.request('getMe', {})

    async def set_webhook(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'url': settings.webhook_url,
            'allowed_updates': ['message', 'callback_query'],
        }
        if settings.webhook_secret:
            payload['secret_token'] = settings.webhook_secret
        return await self.request('setWebhook', payload)

    async def send_text(
        self,
        chat_id: int | str,
        text: str,
        *,
        entities: list[dict[str, Any]] | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {'chat_id': chat_id, 'text': text}
        if entities:
            payload['entities'] = entities
        if reply_markup:
            payload['reply_markup'] = reply_markup
        return await self.request('sendMessage', payload)

    async def edit_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | bool:
        payload: dict[str, Any] = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
        if reply_markup:
            payload['reply_markup'] = reply_markup
        return await self.request('editMessageText', payload)

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self.request('getFile', {'file_id': file_id})

    async def download_file(self, file_path: str, destination: Path) -> Path:
        url = f'https://api.telegram.org/file/bot{self.token}/{file_path}'
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.content)
        return destination

    async def copy_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'chat_id': chat_id,
            'from_chat_id': from_chat_id,
            'message_id': message_id,
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup
        return await self.request('copyMessage', payload)
