# 信鸽 - Telegram 账号托管群发助手

Telegram 账号托管群发助手。

## 功能

- QR 登录 Telegram 账号
- Mini App 手机号登录
- 目标、模板、任务管理
- 单次 / 每日群发

## 配置

复制配置文件：

```bash
cp .env.example .env
python scripts/gen-session-key.py
```

填写 `.env`：

| 变量 | 必填 | 说明 |
|---|---:|---|
| `BOT_TOKEN` | 是 | Telegram Bot Token |
| `WEBHOOK_BASE_URL` | 是 | 外网访问地址，例如 `https://example.com/xinge` |
| `WEBHOOK_SECRET` | 是 | Webhook 路径密钥 |
| `TELEGRAM_API_ID` | 是 | Telegram API ID |
| `TELEGRAM_API_HASH` | 是 | Telegram API Hash |
| `SESSION_ENCRYPTION_KEY` | 是 | 会话加密密钥，至少 32 字符 |
| `WEB_HOST` | 否 | 默认 `0.0.0.0` |
| `WEB_PORT` | 否 | 默认 `3510` |
| `DB_PATH` | 否 | 默认 `data/app.db` |
| `LOG_LEVEL` | 否 | 默认 `INFO` |
| `DEFAULT_TIMEZONE` | 否 | 默认 `Asia/Shanghai` |
| `SEND_MIN_INTERVAL_SECONDS` | 否 | 发送间隔，默认 `3` |

检查配置：

```bash
python scripts/check-env.py
```

## 运行

本地：

```bash
bash scripts/dev.sh
```

Docker：

```bash
docker compose up -d --build
```

systemd：

```bash
cp scripts/xinge-broadcast-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now xinge-broadcast-bot
```

## 数据

- 数据库：`data/app.db`
- 日志：`logs/`
- 敏感配置：`.env`

这些文件不要提交。
