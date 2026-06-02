from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REQUIRED = [
    'BOT_TOKEN',
    'WEBHOOK_BASE_URL',
    'WEBHOOK_SECRET',
    'TELEGRAM_API_ID',
    'TELEGRAM_API_HASH',
    'SESSION_ENCRYPTION_KEY',
]

missing = [key for key in REQUIRED if not os.getenv(key)]
if missing:
    print('Missing required environment variables:')
    for key in missing:
        print(f'  - {key}')
    sys.exit(1)

if len(os.getenv('SESSION_ENCRYPTION_KEY', '')) < 32:
    print('SESSION_ENCRYPTION_KEY is too short. Use at least 32 random characters.')
    sys.exit(1)

for path in ['data', 'logs']:
    Path(path).mkdir(exist_ok=True)

print('Environment looks good.')
