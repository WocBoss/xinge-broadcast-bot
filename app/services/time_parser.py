from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings


@dataclass(frozen=True)
class ScheduleRule:
    kind: str
    value: dict

    def to_json(self) -> dict:
        return {'kind': self.kind, 'value': self.value}


class TimeParser:
    """Parse send rules and format timestamps in Asia/Shanghai."""

    DAILY_TIME_RE = re.compile(r'([01]?\d|2[0-3]):([0-5]\d)')
    INTERVAL_RE = re.compile(r'(?:每|间隔)\s*(\d+)\s*(分钟|分|小时|时|天|日)')
    AFTER_RE = re.compile(r'(?:单次|一次)?\s*(\d+)\s*(分钟|分|小时|时|天|日)后')
    ONCE_AT_RE = re.compile(r'(?:单次|一次)\s*(?:(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*)?([01]?\d|2[0-3]):([0-5]\d)')

    def parse_rule(self, text: str, timezone: str | None = None) -> ScheduleRule:
        normalized = (text or '').strip().replace('，', ',').replace('；', ';')
        if not normalized:
            raise ValueError('请选择发送规则')

        after = self.AFTER_RE.search(normalized)
        if after:
            amount = int(after.group(1))
            unit = after.group(2)
            minutes = self._interval_to_minutes(amount, unit)
            if minutes < 1:
                raise ValueError('时间太短')
            return ScheduleRule(kind='once_after', value={'minutes': minutes})

        once_at = self.ONCE_AT_RE.search(normalized)
        if once_at:
            year, month, day, hour, minute = once_at.groups()
            value = {'time': f'{int(hour):02d}:{minute}'}
            if year and month and day:
                value['date'] = f'{int(year):04d}-{int(month):02d}-{int(day):02d}'
            return ScheduleRule(kind='once_at', value=value)

        interval = self.INTERVAL_RE.search(normalized)
        if interval:
            amount = int(interval.group(1))
            unit = interval.group(2)
            minutes = self._interval_to_minutes(amount, unit)
            if minutes < 1:
                raise ValueError('间隔时间太短')
            return ScheduleRule(kind='interval', value={'minutes': minutes})

        times = [f'{int(h):02d}:{m}' for h, m in self.DAILY_TIME_RE.findall(normalized)]
        if times:
            unique_times = list(dict.fromkeys(times))
            return ScheduleRule(kind='daily', value={'times': unique_times})

        raise ValueError('发送规则格式不对。例：单次10分钟后、单次2026-06-02 10:00、每天10:00、每10分钟')

    def initial_next_run_at(self, rule: ScheduleRule, timezone: str | None = None) -> str:
        tz = ZoneInfo(timezone or settings.default_timezone)
        now = datetime.now(tz)
        return self.next_run_after(rule, now, timezone).isoformat()

    def next_run_after(self, rule: ScheduleRule, after: datetime, timezone: str | None = None) -> datetime:
        tz = ZoneInfo(timezone or settings.default_timezone)
        base = after.astimezone(tz)

        if rule.kind == 'once_after':
            return base + timedelta(minutes=int(rule.value['minutes']))

        if rule.kind == 'once_at':
            hour, minute = [int(x) for x in rule.value['time'].split(':', 1)]
            if rule.value.get('date'):
                year, month, day = [int(x) for x in rule.value['date'].split('-', 2)]
                candidate = base.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            else:
                candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= base:
                    candidate += timedelta(days=1)
            if candidate <= base:
                raise ValueError('单次发送时间已经过去')
            return candidate

        if rule.kind == 'interval':
            return base + timedelta(minutes=int(rule.value['minutes']))

        if rule.kind == 'daily':
            candidates: list[datetime] = []
            for time_text in rule.value.get('times', []):
                hour, minute = [int(x) for x in time_text.split(':', 1)]
                candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= base:
                    candidate += timedelta(days=1)
                candidates.append(candidate)
            if candidates:
                return min(candidates)

        raise ValueError('未知发送规则')

    def describe_rule(self, rule_json: dict | None) -> str:
        if not rule_json:
            return '未知规则'
        kind = rule_json.get('kind')
        value = rule_json.get('value') or {}
        if kind == 'once_after':
            return self._describe_minutes(int(value.get('minutes') or 0)) + '后，仅一次'
        if kind == 'once_at':
            return f"单次{value.get('date') + ' ' if value.get('date') else ''}{value.get('time')}"
        if kind == 'daily':
            return '每天' + '、'.join(value.get('times') or [])
        if kind == 'interval':
            return '每' + self._describe_minutes(int(value.get('minutes') or 0))
        return '未知规则'

    def rule_text_from_json(self, rule_json: dict | None) -> str:
        if not rule_json:
            return ''
        kind = rule_json.get('kind')
        value = rule_json.get('value') or {}
        if kind == 'once_after':
            return f"单次{self._describe_minutes(int(value.get('minutes') or 0))}后"
        if kind == 'once_at':
            return f"单次{value.get('date') + ' ' if value.get('date') else ''}{value.get('time')}"
        if kind == 'daily':
            return ' '.join(f'每天{t}' for t in value.get('times') or [])
        if kind == 'interval':
            return f"每{self._describe_minutes(int(value.get('minutes') or 0))}"
        return ''

    def format_dt(self, iso_text: str | None, timezone: str | None = None) -> str:
        if not iso_text:
            return '-'
        dt = datetime.fromisoformat(iso_text)
        tz = ZoneInfo(timezone or settings.default_timezone)
        return dt.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')

    def _describe_minutes(self, minutes: int) -> str:
        if minutes % 1440 == 0:
            return f'{minutes // 1440}天'
        if minutes % 60 == 0:
            return f'{minutes // 60}小时'
        return f'{minutes}分钟'

    def _interval_to_minutes(self, amount: int, unit: str) -> int:
        if unit in ('分钟', '分'):
            return amount
        if unit in ('小时', '时'):
            return amount * 60
        if unit in ('天', '日'):
            return amount * 1440
        raise ValueError('未知间隔单位')
