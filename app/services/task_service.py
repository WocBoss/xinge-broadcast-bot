from __future__ import annotations

from app.config import settings
from app.repositories.account_sessions import AccountSessionRepo
from app.repositories.targets import TargetRepo
from app.repositories.templates import TemplateRepo
from app.repositories.tasks import TaskRepo, ScheduleTask
from app.services.time_parser import TimeParser


class TaskService:
    def __init__(self):
        self.sessions = AccountSessionRepo()
        self.templates = TemplateRepo()
        self.targets = TargetRepo()
        self.tasks = TaskRepo()
        self.time_parser = TimeParser()

    async def create_task_from_text(
        self,
        owner_user_id: int,
        template_id: int,
        target_ids: list[int],
        rule_text: str,
        timezone: str | None = None,
    ) -> ScheduleTask:
        session = await self.sessions.get_by_owner(owner_user_id)
        if not session or session.status != 'connected':
            raise ValueError('请先连接 Telegram 账号')
        template = await self.templates.get(template_id)
        if not template or template.owner_user_id != owner_user_id:
            raise ValueError('模板不存在')
        if not target_ids:
            raise ValueError('请至少选择一个目标')
        tz = timezone or settings.default_timezone
        rule = self.time_parser.parse_rule(rule_text, tz)
        next_run_at = self.time_parser.initial_next_run_at(rule, tz)
        return await self.tasks.create(owner_user_id, template_id, target_ids, rule.to_json(), next_run_at, tz)

    async def list_tasks(self, owner_user_id: int) -> list[ScheduleTask]:
        return await self.tasks.list_by_owner(owner_user_id)

    async def get_task(self, owner_user_id: int, task_id: int) -> ScheduleTask:
        task = await self.tasks.get(task_id)
        if not task or task.owner_user_id != owner_user_id:
            raise ValueError('任务不存在')
        return task

    async def pause_task(self, owner_user_id: int, task_id: int) -> ScheduleTask:
        task = await self.tasks.set_status_by_owner(task_id, owner_user_id, 'paused')
        if not task or task.owner_user_id != owner_user_id:
            raise ValueError('任务不存在')
        return task

    async def resume_task(self, owner_user_id: int, task_id: int) -> ScheduleTask:
        task = await self.get_task(owner_user_id, task_id)
        rule = self.time_parser.parse_rule(self.time_parser.rule_text_from_json(task.schedule_rule), task.timezone)
        next_run_at = self.time_parser.initial_next_run_at(rule, task.timezone)
        updated = await self.tasks.update_rule(task_id, owner_user_id, task.schedule_rule, next_run_at)
        if not updated:
            raise ValueError('任务不存在')
        return updated

    async def update_rule(self, owner_user_id: int, task_id: int, rule_text: str) -> ScheduleTask:
        task = await self.get_task(owner_user_id, task_id)
        rule = self.time_parser.parse_rule(rule_text, task.timezone)
        next_run_at = self.time_parser.initial_next_run_at(rule, task.timezone)
        updated = await self.tasks.update_rule(task_id, owner_user_id, rule.to_json(), next_run_at)
        if not updated:
            raise ValueError('任务不存在')
        return updated

    async def delete_task(self, owner_user_id: int, task_id: int) -> None:
        deleted = await self.tasks.delete(task_id, owner_user_id)
        if not deleted:
            raise ValueError('任务不存在')
