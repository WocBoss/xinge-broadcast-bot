from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from app.config import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS account_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'mtproto',
    status TEXT NOT NULL DEFAULT 'disconnected',
    phone TEXT,
    display_name TEXT,
    session_encrypted TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    target_input TEXT NOT NULL,
    target_type TEXT,
    target_peer_json TEXT NOT NULL DEFAULT '{}',
    target_title TEXT,
    target_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    last_check_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    raw_message_json TEXT NOT NULL,
    text TEXT,
    entities_json TEXT NOT NULL DEFAULT '[]',
    media_json TEXT NOT NULL DEFAULT '{}',
    caption TEXT,
    caption_entities_json TEXT NOT NULL DEFAULT '[]',
    reply_markup_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schedule_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    template_id INTEGER NOT NULL,
    target_ids_json TEXT NOT NULL,
    schedule_rule_json TEXT NOT NULL DEFAULT '{}',
    next_run_at TEXT,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(template_id) REFERENCES message_templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS send_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    scheduled_time TEXT NOT NULL,
    actual_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    message_id INTEGER,
    error_code TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_id) REFERENCES schedule_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_account_sessions_owner ON account_sessions(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_targets_owner ON targets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_templates_owner ON message_templates(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_owner_status ON schedule_tasks(owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_send_logs_task ON send_logs(task_id);
"""


async def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
    finally:
        await db.close()
