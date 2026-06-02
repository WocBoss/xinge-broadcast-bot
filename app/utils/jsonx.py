from __future__ import annotations

import json
from typing import Any, Iterable


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}
