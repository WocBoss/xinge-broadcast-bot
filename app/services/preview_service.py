from __future__ import annotations

from app.clients.telegram_bot_api import TelegramBotApiClient
from app.repositories.templates import TemplateRepo


class PreviewService:
    def __init__(self):
        self.tg = TelegramBotApiClient()
        self.templates = TemplateRepo()

    async def preview_to_owner(self, owner_user_id: int, template_id: int) -> None:
        template = await self.templates.get(template_id)
        if not template or template.owner_user_id != owner_user_id:
            raise ValueError('模板不存在')
        raw = template.raw_message
        if raw.get('chat') and raw.get('message_id'):
            await self.tg.copy_message(
                chat_id=owner_user_id,
                from_chat_id=raw['chat']['id'],
                message_id=raw['message_id'],
                reply_markup=template.reply_markup or None,
            )
        else:
            await self.tg.send_text(
                chat_id=owner_user_id,
                text=template.text or template.caption or '(空内容)',
                entities=template.entities or None,
                reply_markup=template.reply_markup or None,
            )

    async def send_now(self, owner_user_id: int, template_id: int, target_id: int) -> dict:
        raise RuntimeError('即时发送入口已禁用，请通过任务调度使用账号托管发送器')
