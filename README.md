# 信鸽 - Telegram 账号托管群发助手

信鸽是 TBaaS 旗下的 Telegram 账号托管群发工具，用于把个人或业务 Telegram 账号连接到服务端，统一管理发送目标、消息模板和定时发送任务。

官方频道：[@TBaaS_cc](https://t.me/TBaaS_cc)

## 适合场景

- 需要定时向多个 Telegram 群组、频道或用户发送通知
- 需要保存常用群发内容，减少重复操作
- 需要用自己的 Telegram 账号发送，而不是 Bot 身份发送
- 需要简单部署一套私有的账号托管发送服务

## 核心能力

### 账号连接

- 通过 Telegram Mini App 完成手机号登录
- 支持验证码和 2FA 密码流程
- 登录成功后保存加密后的 Telegram 会话
- 支持随时断开账号并删除本地登录态

### 目标管理

- 支持保存 `@username` 和 `t.me` 链接
- 自动解析目标类型和标题
- 检测当前账号是否具备发送权限
- 每个 Telegram 用户的数据独立隔离

### 模板管理

- 支持保存文字消息
- 支持保存图片、视频等媒体消息及说明文字
- 支持模板预览、编辑和删除
- 创建任务时可复用已保存模板

### 定时群发

- 支持单次发送
- 支持每日固定时间发送
- 支持间隔发送
- 支持暂停、恢复、修改和删除任务
- 发送记录落库，失败原因可追踪

支持的规则示例：

```txt
单次10分钟后
单次2026-06-02 10:00
每天10:00
每天10:00 18:00
每10分钟
每2小时
```

默认时区为 `Asia/Shanghai`，可通过环境变量调整。

## 使用流程

1. 在 Bot 中发送 `/start`
2. 首次使用时阅读账号托管须知
3. 点击「连接账号」并打开 Mini App 登录页
4. 输入手机号、验证码；如账号开启 2FA，再输入 2FA 密码
5. 添加发送目标
6. 保存群发内容
7. 创建定时任务

## 部署

### 1. 准备配置

```bash
cp .env.example .env
python scripts/gen-session-key.py
```

把生成的密钥填入 `.env` 的 `SESSION_ENCRYPTION_KEY`。

必填配置：

| 变量 | 说明 |
|---|---|
| `BOT_TOKEN` | Telegram Bot Token |
| `WEBHOOK_BASE_URL` | 服务外网地址，例如 `https://example.com/xinge` |
| `WEBHOOK_SECRET` | Webhook 路径密钥 |
| `TELEGRAM_API_ID` | Telegram API ID |
| `TELEGRAM_API_HASH` | Telegram API Hash |
| `SESSION_ENCRYPTION_KEY` | 会话加密密钥，至少 32 字符 |

可选配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WEB_HOST` | `0.0.0.0` | Web 服务监听地址 |
| `WEB_PORT` | `3510` | Web 服务端口 |
| `DB_PATH` | `data/app.db` | SQLite 数据库路径 |
| `LOG_LEVEL` | `INFO` | 日志等级 |
| `DEFAULT_TIMEZONE` | `Asia/Shanghai` | 默认任务时区 |
| `SEND_MIN_INTERVAL_SECONDS` | `3` | 单次发送间隔 |

检查配置：

```bash
python scripts/check-env.py
```

### 2. 本地运行

```bash
bash scripts/dev.sh
```

### 3. Docker 运行

```bash
docker compose up -d --build
```

### 4. systemd 运行

按实际部署路径修改 `scripts/xinge-broadcast-bot.service` 后安装：

```bash
cp scripts/xinge-broadcast-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now xinge-broadcast-bot
```

## Webhook 与 Mini App

服务会使用 `WEBHOOK_BASE_URL` 生成地址：

```txt
{WEBHOOK_BASE_URL}/telegram
{WEBHOOK_BASE_URL}/login
```

如果使用反向代理，请保证外网可以访问 `/telegram` 和 `/login`。

## 安全说明

- 验证码和 2FA 密码只用于当次登录，不写入数据库
- Telegram 登录态使用 `SESSION_ENCRYPTION_KEY` 加密保存
- 用户可在 Bot 内断开账号，删除本地登录态
- 用户也可在 Telegram「设置 → 设备」中移除对应登录设备
- 请合理设置发送频率，频繁发送可能触发 Telegram 风控

## 开源协议

MIT License
