from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedTargetInput:
    raw: str
    kind: str
    username: str | None = None
    invite_hash: str | None = None


class TargetParser:
    USERNAME_RE = re.compile(r'^(?:@|https?://t\.me/)([A-Za-z0-9_]{5,32})/?$')
    INVITE_RE = re.compile(r'^https?://t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]+)$')

    def parse(self, value: str) -> ParsedTargetInput:
        raw = value.strip()
        m = self.USERNAME_RE.match(raw)
        if m:
            return ParsedTargetInput(raw=raw, kind='username', username=m.group(1))
        m = self.INVITE_RE.match(raw)
        if m:
            return ParsedTargetInput(raw=raw, kind='invite_link', invite_hash=m.group(1))
        if raw.lstrip('-').isdigit():
            return ParsedTargetInput(raw=raw, kind='chat_id')
        return ParsedTargetInput(raw=raw, kind='unknown')
