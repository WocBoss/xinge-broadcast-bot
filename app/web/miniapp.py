from __future__ import annotations

from pathlib import Path

from aiohttp import web
from loguru import logger

from app.clients.telegram_bot_api import TelegramBotApiClient
from app.config import settings
from app.services.account_session_service import AccountSessionService
from app.services.miniapp_auth import verify_init_data

WEB_DIR = Path(__file__).resolve().parent
LOGIN_TEMPLATE = WEB_DIR / 'templates' / 'login.html'
STATIC_DIR = WEB_DIR / 'static'


class MiniAppRoutes:
    def __init__(self):
        self.sessions = AccountSessionService()
        self.bot = TelegramBotApiClient()

    async def login_page(self, request: web.Request) -> web.Response:
        return web.FileResponse(LOGIN_TEMPLATE)

    async def begin_phone(self, request: web.Request) -> web.Response:
        try:
            user, payload = await self._parse(request)
            session = await self.sessions.begin_phone_login(int(user['id']), str(payload.get('phone') or ''))
            return web.json_response({'ok': True, 'status': session.status})
        except Exception as e:
            logger.warning(f'MiniApp begin phone failed: {e}')
            return web.json_response({'ok': False, 'error': str(e)}, status=400)

    async def confirm_code(self, request: web.Request) -> web.Response:
        try:
            user, payload = await self._parse(request)
            try:
                session = await self.sessions.confirm_phone_code(int(user['id']), str(payload.get('code') or ''))
                await self._edit_login_message(user, payload, session)
                return web.json_response({'ok': True, 'status': session.status})
            except ValueError as e:
                if '2FA' in str(e) or '二步验证' in str(e):
                    return web.json_response({'ok': True, 'next': 'password'})
                raise
        except Exception as e:
            logger.warning(f'MiniApp confirm code failed: {e}')
            return web.json_response({'ok': False, 'error': str(e)}, status=400)

    async def confirm_password(self, request: web.Request) -> web.Response:
        try:
            user, payload = await self._parse(request)
            session = await self.sessions.confirm_password(int(user['id']), str(payload.get('password') or ''))
            await self._edit_login_message(user, payload, session)
            return web.json_response({'ok': True, 'status': session.status})
        except Exception as e:
            logger.warning(f'MiniApp confirm password failed: {e}')
            return web.json_response({'ok': False, 'error': str(e)}, status=400)

    async def _edit_login_message(self, user: dict, payload: dict, session) -> None:
        message_id = payload.get('messageId')
        if not message_id:
            return
        try:
            await self.bot.edit_text(
                chat_id=int(user['id']),
                message_id=int(message_id),
                text=f'账号已连接：{session.display_name or session.phone or "Telegram 账号"}',
                reply_markup={
                    'inline_keyboard': [
                        [{'text': '添加目标', 'callback_data': 'add_target'}, {'text': '保存群发内容', 'callback_data': 'add_template'}],
                        [{'text': '创建定时任务', 'callback_data': 'newtask'}],
                        [{'text': '首页', 'callback_data': 'home'}],
                    ]
                },
            )
        except Exception as e:
            logger.warning(f'Edit login message failed: {e}')

    async def _parse(self, request: web.Request) -> tuple[dict, dict]:
        payload = await request.json()
        user = verify_init_data(str(payload.get('initData') or ''))
        return user, payload


def setup_miniapp_routes(app: web.Application) -> None:
    routes = MiniAppRoutes()
    app.router.add_get('/login', routes.login_page)
    app.router.add_static('/static/', STATIC_DIR)
    app.router.add_post('/api/login/phone', routes.begin_phone)
    app.router.add_post('/api/login/code', routes.confirm_code)
    app.router.add_post('/api/login/password', routes.confirm_password)
