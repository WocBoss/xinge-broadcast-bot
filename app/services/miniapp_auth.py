from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from app.config import settings


class MiniAppAuthError(ValueError):
    """Raised when Telegram Mini App initData cannot be trusted."""


def verify_init_data(init_data: str, *, max_age_seconds: int = 3600) -> dict:
    """Verify Telegram Mini App initData and return parsed user.

    Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise MiniAppAuthError('缺少 Telegram 登录信息')

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop('hash', None)
    if not received_hash:
        raise MiniAppAuthError('缺少签名')

    data_check_string = '\n'.join(f'{key}={value}' for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b'WebAppData', settings.bot_token.encode('utf-8'), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise MiniAppAuthError('Telegram 登录签名无效')

    auth_date = int(pairs.get('auth_date') or '0')
    if not auth_date or time.time() - auth_date > max_age_seconds:
        raise MiniAppAuthError('Telegram 登录信息已过期，请重新打开页面')

    user_raw = pairs.get('user')
    if not user_raw:
        raise MiniAppAuthError('缺少用户信息')
    return json.loads(user_raw)
