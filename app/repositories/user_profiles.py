from __future__ import annotations

from app.db import get_db


class UserProfileRepo:
    async def has_seen_notice(self, owner_user_id: int) -> bool:
        async with get_db() as db:
            cur = await db.execute('SELECT notice_seen_at FROM user_profiles WHERE owner_user_id=?', (owner_user_id,))
            row = await cur.fetchone()
            return bool(row and row['notice_seen_at'])

    async def mark_notice_seen(self, owner_user_id: int) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO user_profiles (owner_user_id, notice_seen_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    notice_seen_at=COALESCE(user_profiles.notice_seen_at, CURRENT_TIMESTAMP),
                    updated_at=CURRENT_TIMESTAMP
                """,
                (owner_user_id,),
            )
            await db.commit()
