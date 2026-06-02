from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from loguru import logger

from app.config import settings
from app.repositories.account_sessions import AccountSessionRepo
from app.repositories.targets import TargetRepo
from app.repositories.templates import TemplateRepo
from app.repositories.tasks import TaskRepo, SendLogRepo, ScheduleTask
from app.services.account_sender_service import AccountSenderService
from app.services.time_parser import ScheduleRule, TimeParser


class BroadcastScheduler:
    def __init__(self):
        self.tasks = TaskRepo()
        self.logs = SendLogRepo()
        self.targets = TargetRepo()
        self.templates = TemplateRepo()
        self.sessions = AccountSessionRepo()
        self.sender = AccountSenderService()
        self.time_parser = TimeParser()
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        logger.info('Broadcast scheduler started')
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                logger.exception(f'Scheduler tick failed: {e}')
            await asyncio.sleep(30)

    async def stop(self) -> None:
        self._running = False

    async def tick(self) -> None:
        now = datetime.now(ZoneInfo(settings.default_timezone))
        for task in await self.tasks.list_active():
            if not task.next_run_at or not task.schedule_rule:
                continue
            next_run = datetime.fromisoformat(task.next_run_at)
            if next_run <= now:
                await self._dispatch_task_time(task.id, task.next_run_at)
                await self._schedule_next_run(task, next_run)

    async def _schedule_next_run(self, task: ScheduleTask, last_run: datetime) -> None:
        if task.schedule_rule.get('kind') in ('once_after', 'once_at'):
            await self.tasks.set_status(task.id, 'completed')
            return
        rule = ScheduleRule(kind=task.schedule_rule.get('kind'), value=task.schedule_rule.get('value') or {})
        next_run = self.time_parser.next_run_after(rule, last_run, task.timezone)
        await self.tasks.update_next_run(task.id, next_run.isoformat())

    async def _dispatch_task_time(self, task_id: int, send_time: str) -> None:
        task = await self.tasks.get(task_id)
        if not task:
            return
        session = await self.sessions.get_by_owner(task.owner_user_id)
        template = await self.templates.get(task.template_id)
        if not session or not template:
            return

        for target_id in task.target_ids:
            target = await self.targets.get(target_id)
            log_id = await self.logs.create(task.id, target_id, send_time)
            try:
                if not target or target.status != 'sendable':
                    raise RuntimeError(target.last_error if target else '目标不存在或不可发送')
                result = await self.sender.send_template(session=session, target=target, template=template)
                await self.logs.finish(log_id, status='sent', message_id=result.get('message_id'))
                await asyncio.sleep(settings.send_min_interval_seconds)
            except Exception as e:
                logger.warning(f'Send failed task={task.id} target={target_id}: {e}')
                await self.logs.finish(log_id, status='failed', error_message=str(e))
