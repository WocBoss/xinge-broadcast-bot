from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db import get_db
from app.utils.jsonx import dumps, loads, row_to_dict


@dataclass
class ScheduleTask:
    id: int
    owner_user_id: int
    template_id: int
    target_ids: list[int]
    schedule_rule: dict
    next_run_at: str | None
    timezone: str
    status: str


class TaskRepo:
    async def create(
        self,
        owner_user_id: int,
        template_id: int,
        target_ids: list[int],
        schedule_rule: dict,
        next_run_at: str,
        timezone: str,
    ) -> ScheduleTask:
        async with get_db() as db:
            cur = await db.execute(
                """
                INSERT INTO schedule_tasks (
                    owner_user_id, template_id, target_ids_json, schedule_rule_json, next_run_at, timezone
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (owner_user_id, template_id, dumps(target_ids), dumps(schedule_rule), next_run_at, timezone),
            )
            await db.commit()
            return await self.get(cur.lastrowid)

    async def list_active(self) -> list[ScheduleTask]:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM schedule_tasks WHERE status='active' ORDER BY id")
            return [self._map(r) for r in await cur.fetchall()]

    async def list_by_owner(self, owner_user_id: int) -> list[ScheduleTask]:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM schedule_tasks WHERE owner_user_id=? ORDER BY id DESC", (owner_user_id,))
            return [self._map(r) for r in await cur.fetchall()]

    async def set_status(self, task_id: int, status: str) -> None:
        async with get_db() as db:
            await db.execute("UPDATE schedule_tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, task_id))
            await db.commit()

    async def set_status_by_owner(self, task_id: int, owner_user_id: int, status: str) -> ScheduleTask | None:
        async with get_db() as db:
            await db.execute(
                "UPDATE schedule_tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_user_id=?",
                (status, task_id, owner_user_id),
            )
            await db.commit()
        return await self.get(task_id)

    async def update_rule(self, task_id: int, owner_user_id: int, schedule_rule: dict, next_run_at: str) -> ScheduleTask | None:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE schedule_tasks SET schedule_rule_json=?, next_run_at=?, status='active', updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND owner_user_id=?
                """,
                (dumps(schedule_rule), next_run_at, task_id, owner_user_id),
            )
            await db.commit()
        return await self.get(task_id)

    async def delete(self, task_id: int, owner_user_id: int) -> bool:
        async with get_db() as db:
            cur = await db.execute("DELETE FROM schedule_tasks WHERE id=? AND owner_user_id=?", (task_id, owner_user_id))
            await db.commit()
            return cur.rowcount > 0

    async def update_next_run(self, task_id: int, next_run_at: str) -> None:
        async with get_db() as db:
            await db.execute(
                "UPDATE schedule_tasks SET next_run_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (next_run_at, task_id),
            )
            await db.commit()

    async def get(self, task_id: int) -> ScheduleTask | None:
        async with get_db() as db:
            cur = await db.execute("SELECT * FROM schedule_tasks WHERE id=?", (task_id,))
            return self._map(await cur.fetchone())

    def _map(self, row: Any) -> ScheduleTask | None:
        if not row:
            return None
        d = row_to_dict(row)
        return ScheduleTask(
            id=d['id'],
            owner_user_id=d['owner_user_id'],
            template_id=d['template_id'],
            target_ids=loads(d.get('target_ids_json'), []),
            schedule_rule=loads(d.get('schedule_rule_json'), {}),
            next_run_at=d.get('next_run_at'),
            timezone=d['timezone'],
            status=d['status'],
        )


class SendLogRepo:
    async def create(self, task_id: int, target_id: int, scheduled_time: str, status: str = 'pending') -> int:
        async with get_db() as db:
            cur = await db.execute(
                "INSERT INTO send_logs (task_id, target_id, scheduled_time, status) VALUES (?, ?, ?, ?)",
                (task_id, target_id, scheduled_time, status),
            )
            await db.commit()
            return cur.lastrowid

    async def finish(self, log_id: int, *, status: str, message_id: int | None = None, error_code: str | None = None, error_message: str | None = None) -> None:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE send_logs SET status=?, message_id=?, error_code=?, error_message=?,
                    actual_time=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, message_id, error_code, error_message, log_id),
            )
            await db.commit()
