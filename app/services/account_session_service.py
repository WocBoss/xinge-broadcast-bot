from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet
from loguru import logger
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError, PasswordHashInvalidError
from telethon.sessions import StringSession
from telethon.tl.custom.qrlogin import QRLogin

from app.config import settings
from app.repositories.account_sessions import AccountSessionRepo, AccountSession


@dataclass
class QrLoginState:
    client: TelegramClient
    qr_login: QRLogin
    wait_task: asyncio.Task


@dataclass
class PhoneLoginState:
    client: TelegramClient
    phone: str
    phone_code_hash: str


class AccountSessionService:
    _qr_states: dict[int, QrLoginState] = {}
    _phone_states: dict[int, PhoneLoginState] = {}

    def __init__(self):
        self.repo = AccountSessionRepo()

    async def get_session(self, owner_user_id: int) -> AccountSession | None:
        return await self.repo.get_by_owner(owner_user_id)

    async def is_connected(self, owner_user_id: int) -> bool:
        session = await self.get_session(owner_user_id)
        return bool(session and session.status == 'connected')

    async def require_connected(self, owner_user_id: int) -> AccountSession:
        session = await self.get_session(owner_user_id)
        if not session or session.status != 'connected':
            raise ValueError('请先连接 Telegram 账号')
        return session

    async def begin_qr_login(self, owner_user_id: int) -> tuple[AccountSession, str | None]:
        blocked = self._validate_config()
        if blocked:
            return await self.repo.upsert_status(owner_user_id, status='blocked', last_error=blocked), None

        await self._close_login_states(owner_user_id)
        client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        qr_login = await client.qr_login()
        wait_task = asyncio.create_task(self._wait_qr_login(owner_user_id, client, qr_login))
        self._qr_states[owner_user_id] = QrLoginState(client=client, qr_login=qr_login, wait_task=wait_task)
        session = await self.repo.upsert_status(owner_user_id, status='qr_waiting', last_error=None)
        return session, qr_login.url

    async def confirm_qr_login(self, owner_user_id: int) -> AccountSession:
        session = await self.get_session(owner_user_id)
        if session and session.status == 'connected':
            await self._close_qr_state(owner_user_id, disconnect_client=False)
            return session

        state = self._qr_states.get(owner_user_id)
        if not state:
            raise ValueError('二维码已失效，请重新生成')
        if not state.wait_task.done():
            raise ValueError('还没有检测到扫码确认，请确认后再点这里')

        try:
            return await state.wait_task
        finally:
            await self._close_qr_state(owner_user_id, disconnect_client=False)

    async def begin_phone_login(self, owner_user_id: int, phone: str) -> AccountSession:
        blocked = self._validate_config()
        if blocked:
            return await self.repo.upsert_status(owner_user_id, status='blocked', last_error=blocked)
        normalized_phone = phone.strip().replace(' ', '')
        if not normalized_phone.startswith('+') or len(normalized_phone) < 8:
            raise ValueError('手机号格式不对，请带国家区号，例如：+8613800000000')

        await self._close_login_states(owner_user_id)
        client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        sent = await client.send_code_request(normalized_phone)
        self._phone_states[owner_user_id] = PhoneLoginState(client=client, phone=normalized_phone, phone_code_hash=sent.phone_code_hash)
        return await self.repo.upsert_status(owner_user_id, status='phone_code_waiting', phone=normalized_phone, last_error=None)

    async def confirm_phone_code(self, owner_user_id: int, code: str) -> AccountSession:
        state = self._phone_states.get(owner_user_id)
        if not state:
            raise ValueError('登录状态已失效，请重新输入手机号')
        normalized_code = code.strip().replace(' ', '')
        try:
            user = await state.client.sign_in(phone=state.phone, code=normalized_code, phone_code_hash=state.phone_code_hash)
            return await self._persist_logged_in_client(owner_user_id, state.client, user)
        except SessionPasswordNeededError:
            await self.repo.upsert_status(owner_user_id, status='password_waiting', phone=state.phone, last_error=None)
            raise ValueError('该账号开启了二步验证，请发送 2FA 密码')
        except PhoneCodeInvalidError:
            raise ValueError('验证码错误，请重新输入')
        except PhoneCodeExpiredError:
            await self._close_phone_state(owner_user_id)
            raise ValueError('验证码已过期，请重新输入手机号获取')

    async def confirm_password(self, owner_user_id: int, password: str) -> AccountSession:
        state = self._phone_states.get(owner_user_id)
        if not state:
            raise ValueError('登录状态已失效，请重新输入手机号')
        try:
            user = await state.client.sign_in(password=password)
            return await self._persist_logged_in_client(owner_user_id, state.client, user)
        except PasswordHashInvalidError:
            raise ValueError('2FA 密码错误，请重新输入')

    async def disconnect(self, owner_user_id: int) -> None:
        await self._close_login_states(owner_user_id)
        session = await self.get_session(owner_user_id)
        if session and session.status == 'connected' and session.session_encrypted:
            try:
                client = await self.load_client(owner_user_id)
                await client.log_out()
            except Exception as e:
                logger.warning(f'Telegram logout failed owner={owner_user_id}: {e}')
        await self.repo.delete_by_owner(owner_user_id)

    async def load_client(self, owner_user_id: int) -> TelegramClient:
        session = await self.require_connected(owner_user_id)
        if not session.session_encrypted:
            raise ValueError('账号 session 不存在，请重新连接')
        raw_session = self._decrypt(session.session_encrypted)
        client = TelegramClient(StringSession(raw_session), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise ValueError('账号登录已失效，请重新连接')
        return client

    async def _wait_qr_login(self, owner_user_id: int, client: TelegramClient, qr_login: QRLogin) -> AccountSession:
        try:
            user = await qr_login.wait()
            return await self._persist_logged_in_client(owner_user_id, client, user, disconnect=False)
        except asyncio.TimeoutError:
            await self.repo.upsert_status(owner_user_id, status='qr_expired', last_error='二维码已过期，请重新生成')
            raise ValueError('二维码已过期，请重新生成')
        except Exception as e:
            await self.repo.upsert_status(owner_user_id, status='qr_failed', last_error=str(e))
            raise
        finally:
            await client.disconnect()

    async def _persist_logged_in_client(self, owner_user_id: int, client: TelegramClient, user, *, disconnect: bool = True) -> AccountSession:
        raw_session = client.session.save()
        encrypted = self._encrypt(raw_session)
        display_name = ' '.join(
            x for x in [getattr(user, 'first_name', None), getattr(user, 'last_name', None)] if x
        ) or getattr(user, 'username', None) or str(user.id)
        session = await self.repo.upsert_status(
            owner_user_id,
            status='connected',
            phone=getattr(user, 'phone', None),
            display_name=display_name,
            session_encrypted=encrypted,
            last_error=None,
        )
        await self._close_phone_state(owner_user_id, disconnect_client=False)
        if disconnect:
            await client.disconnect()
        return session

    async def _close_login_states(self, owner_user_id: int) -> None:
        await self._close_qr_state(owner_user_id)
        await self._close_phone_state(owner_user_id)

    async def _close_qr_state(self, owner_user_id: int, *, disconnect_client: bool = True) -> None:
        state = self._qr_states.pop(owner_user_id, None)
        if not state:
            return
        if not state.wait_task.done():
            state.wait_task.cancel()
        if disconnect_client and state.client.is_connected():
            await state.client.disconnect()

    async def _close_phone_state(self, owner_user_id: int, *, disconnect_client: bool = True) -> None:
        state = self._phone_states.pop(owner_user_id, None)
        if state and disconnect_client and state.client.is_connected():
            await state.client.disconnect()

    def _validate_config(self) -> str | None:
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            return '服务端尚未配置 Telegram API ID/API Hash，暂时不能连接账号。'
        if not settings.session_encryption_key:
            return '服务端尚未配置 session_encryption_key，禁止保存账号登录态。'
        return None

    def _fernet(self) -> Fernet:
        digest = hashlib.sha256(settings.session_encryption_key.encode('utf-8')).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode('utf-8')).decode('utf-8')

    def _decrypt(self, value: str) -> str:
        return self._fernet().decrypt(value.encode('utf-8')).decode('utf-8')
