from __future__ import annotations

from app.repositories.account_sessions import AccountSessionRepo
from app.repositories.targets import TargetRepo, Target
from app.services.account_sender_service import AccountSenderService
from app.services.target_parser import TargetParser


class TargetService:
    """Target registration for account-hosted sending."""

    def __init__(self):
        self.sessions = AccountSessionRepo()
        self.targets = TargetRepo()
        self.parser = TargetParser()
        self.sender = AccountSenderService()

    async def add_target(self, owner_user_id: int, target_input: str) -> Target:
        session = await self.sessions.get_by_owner(owner_user_id)
        if not session or session.status != 'connected':
            raise ValueError('请先连接 Telegram 账号')
        target = await self.targets.create_pending(owner_user_id, target_input)
        return await self.check_target(target.id)

    async def check_target(self, target_id: int) -> Target:
        target = await self.targets.get(target_id)
        if not target:
            raise ValueError('目标不存在')

        parsed = self.parser.parse(target.target_input)
        if parsed.kind == 'unknown':
            return await self.targets.mark_checked(target.id, status='invalid', last_error='无法识别这个目标，请检查输入是否正确。')

        try:
            peer = await self.sender.resolve_target(target.owner_user_id, target.target_input)
            return await self.targets.mark_checked(
                target.id,
                status='sendable',
                target_type=peer.get('entity_type') or parsed.kind,
                target_peer=peer,
                target_title=peer.get('title'),
                target_username=peer.get('username') or parsed.username,
                last_error=None,
            )
        except Exception as e:
            return await self.targets.mark_checked(
                target.id,
                status='invalid',
                target_type=parsed.kind,
                target_peer={'raw': parsed.raw, 'username': parsed.username, 'invite_hash': parsed.invite_hash},
                target_username=parsed.username,
                last_error=f'当前账号无法访问这个目标：{self._clean_error(e)}',
            )

    async def update_target(self, owner_user_id: int, target_id: int, target_input: str) -> Target:
        target = await self.targets.update_input(target_id, owner_user_id, target_input)
        if not target:
            raise ValueError('目标不存在')
        return await self.check_target(target.id)

    async def delete_target(self, owner_user_id: int, target_id: int) -> None:
        deleted = await self.targets.delete(target_id, owner_user_id)
        if not deleted:
            raise ValueError('目标不存在')

    async def list_targets(self, owner_user_id: int) -> list[Target]:
        return await self.targets.list_by_owner(owner_user_id)

    def _clean_error(self, error: Exception) -> str:
        text = str(error).strip()
        if not text:
            return '请确认用户名/链接正确，且该账号有权限访问。'
        if len(text) > 120:
            return '请确认用户名/链接正确，且该账号有权限访问。'
        return text
