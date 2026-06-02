from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes
import qrcode
import tempfile
from pathlib import Path

from app.bot.keyboards import back_keyboard, confirm_keyboard, home_keyboard, login_method_keyboard, phone_login_keyboard, qr_login_keyboard, rule_examples_keyboard
from app.config import settings
from app.repositories.user_profiles import UserProfileRepo
from app.services.account_session_service import AccountSessionService
from app.services.preview_service import PreviewService
from app.services.target_parser import TargetParser
from app.services.target_service import TargetService
from app.services.task_service import TaskService
from app.services.template_service import TemplateService


class BotHandlers:
    PAGE_SIZE = 6

    def __init__(self):
        self.account_sessions = AccountSessionService()
        self.targets = TargetService()
        self.templates = TemplateService()
        self.tasks = TaskService()
        self.preview = PreviewService()
        self.parser = TargetParser()
        self.user_profiles = UserProfileRepo()
        self.waiting: dict[int, str] = {}
        self.editing_target: dict[int, int] = {}
        self.editing_template: dict[int, int] = {}
        self.draft_template: dict[int, int] = {}
        self.draft_targets: dict[int, list[int]] = {}
        self.editing_task: dict[int, int] = {}
        self.state_message_id: dict[int, int] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not await self.user_profiles.has_seen_notice(user_id):
            await update.message.reply_text(self._custody_notice_text())
            await self.user_profiles.mark_notice_seen(user_id)
        text, keyboard = await self._home_view(user_id)
        await update.message.reply_text(text, reply_markup=keyboard)

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        user_id = update.effective_user.id
        text = (update.message.text or '').strip()
        state = self.waiting.get(user_id)

        if text.startswith('/'):
            text, keyboard = await self._home_view(user_id)
            await update.message.reply_text('不需要命令，直接用按钮操作。\n\n' + text, reply_markup=keyboard)
            return

        if state == 'add_target':
            await self._add_target_message(update.message, user_id, text)
            return
        if state == 'edit_target':
            await self._edit_target_message(update.message, user_id, text)
            return
        if state == 'add_template':
            await self._save_template_message(update.message, user_id)
            return
        if state == 'edit_template':
            await self._edit_template_message(update.message, user_id, text)
            return
        if state == 'task_rule':
            await self._create_task_reply(update.message, user_id, text)
            return
        if state == 'edit_task_rule':
            await self._edit_task_rule_reply(update.message, user_id, text)
            return

        if text and self.parser.parse(text).kind != 'unknown':
            await self._add_target_message(update.message, user_id, text)
            return
        await self._save_template_message(update.message, user_id)

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        user_id = query.from_user.id
        action = query.data or ''

        if action == 'home':
            self._clear_state(user_id)
            await self._edit(query.message, *(await self._home_view(user_id)))
            return

        if action == 'connect_account':
            session = await self.account_sessions.get_session(user_id)
            if session and session.status == 'connected':
                await self._edit(query.message, f'账号已连接：{session.display_name or session.phone or "Telegram 账号"}', self._home_keyboard(True))
                return
            self._clear_state(user_id)
            await self._edit(query.message, '选择登录方式', self._login_method_keyboard())
            return

        if action == 'qr_login':
            session, qr_url = await self.account_sessions.begin_qr_login(user_id)
            if not qr_url:
                await self._edit(query.message, self._connect_account_text(session), self._home_keyboard())
                return
            qr_path = self._make_qr_image(user_id, qr_url)
            await self._edit(
                query.message,
                '双设备扫码登录\n\n请用另一台已登录 Telegram 的设备扫码确认登录。\n\n扫码确认后回到这里，点「我已确认登录」。',
                self._qr_login_keyboard(),
            )
            with qr_path.open('rb') as qr_file:
                await query.message.reply_photo(photo=qr_file, caption='扫码登录 Telegram 账号。二维码短时间内有效。')
            qr_path.unlink(missing_ok=True)
            return

        if action == 'phone_login':
            await self._edit(
                query.message,
                '单设备手机号登录\n\n点击下面按钮打开 Mini App 登录页。\n验证码和 2FA 密码只在网页里输入，不要发到 Telegram 聊天。',
                phone_login_keyboard(f'{settings.webhook_base_url.rstrip("/")}/login?m={query.message.message_id}'),
            )
            return

        if action == 'confirm_qr_login':
            try:
                session = await self.account_sessions.confirm_qr_login(user_id)
                await self._edit(query.message, f'账号已连接：{session.display_name or session.phone or "Telegram 账号"}', self._home_keyboard(True))
            except Exception as e:
                await self._edit(query.message, f'{e}', self._qr_login_keyboard())
            return

        if action == 'disconnect_account':
            session = await self.account_sessions.get_session(user_id)
            if not session or session.status != 'connected':
                await self._edit(query.message, '当前没有连接账号。', self._home_keyboard(False))
                return
            await self.account_sessions.disconnect(user_id)
            await self._edit(query.message, '账号已断开，本地登录态已删除。', self._home_keyboard(False))
            return

        if action == 'add_target':
            self.waiting[user_id] = 'add_target'
            rendered = await self._edit(
                query.message,
                '添加目标\n\n直接发送 @用户名 或 t.me 链接。\n\n发来后我会保存并检测是否可发送。',
                self._back_keyboard(),
            )
            self._remember_state_message(user_id, rendered)
            return

        if action == 'add_template':
            self.waiting[user_id] = 'add_template'
            rendered = await self._edit(
                query.message,
                '保存群发内容\n\n直接发送要群发的文字、图片、视频或带说明的媒体消息。',
                self._back_keyboard(),
            )
            self._remember_state_message(user_id, rendered)
            return

        if action == 'targets':
            await self._edit(query.message, *(await self._targets_view(user_id)))
            return

        if action == 'templates':
            await self._edit(query.message, *(await self._templates_view(user_id)))
            return

        if action == 'tasks':
            await self._edit(query.message, *(await self._tasks_view(user_id)))
            return

        if action.startswith('task:'):
            await self._edit(query.message, *(await self._task_detail_view(user_id, int(action.split(':', 1)[1]))))
            return

        if action.startswith('pause_task:'):
            task_id = int(action.split(':', 1)[1])
            try:
                await self.tasks.pause_task(user_id, task_id)
                await self._edit(query.message, *(await self._task_detail_view(user_id, task_id)))
            except Exception as e:
                await self._edit(query.message, f'暂停失败：{e}', self._home_keyboard())
            return

        if action.startswith('resume_task:'):
            task_id = int(action.split(':', 1)[1])
            try:
                await self.tasks.resume_task(user_id, task_id)
                await self._edit(query.message, *(await self._task_detail_view(user_id, task_id)))
            except Exception as e:
                await self._edit(query.message, f'恢复失败：{e}', self._home_keyboard())
            return

        if action.startswith('edit_task_rule:'):
            task_id = int(action.split(':', 1)[1])
            self.waiting[user_id] = 'edit_task_rule'
            self.editing_task[user_id] = task_id
            rendered = await self._edit(query.message, f'修改任务 #{task_id} 的发送规则\n\n点一个规则，或者直接发送自定义规则。', self._rule_examples_keyboard(prefix=f'update_rule:{task_id}:', back_to=f'task:{task_id}'))
            self._remember_state_message(user_id, rendered)
            return

        if action.startswith('update_rule:'):
            _, task_id_text, rule_text = action.split(':', 2)
            task_id = int(task_id_text)
            try:
                task = await self.tasks.update_rule(user_id, task_id, rule_text)
                self._clear_state(user_id)
                await self._edit(query.message, self._task_updated_text(task), self._task_detail_keyboard(task))
            except Exception as e:
                await self._edit(query.message, f'修改失败：{e}', self._home_keyboard())
            return

        if action.startswith('delete_task:'):
            task_id = int(action.split(':', 1)[1])
            await self._edit(query.message, f'确认删除任务 #{task_id}？', self._confirm_keyboard(f'confirm_delete_task:{task_id}', f'task:{task_id}'))
            return

        if action.startswith('confirm_delete_task:'):
            task_id = int(action.split(':', 1)[1])
            try:
                await self.tasks.delete_task(user_id, task_id)
                await self._edit(query.message, f'任务 #{task_id} 已删除。', self._home_keyboard())
            except Exception as e:
                await self._edit(query.message, f'删除失败：{e}', self._home_keyboard())
            return

        if action == 'newtask':
            await self._start_task(query.message, user_id)
            return

        if action.startswith('pick_template:'):
            template_id = int(action.split(':', 1)[1])
            self.draft_template[user_id] = template_id
            await self._edit(query.message, *(await self._pick_targets_view(user_id)))
            return

        if action.startswith('toggle_target:'):
            target_id = int(action.split(':', 1)[1])
            selected = self.draft_targets.setdefault(user_id, [])
            if target_id in selected:
                selected.remove(target_id)
            else:
                selected.append(target_id)
            await self._edit(query.message, *(await self._pick_targets_view(user_id)))
            return

        if action == 'task_rule':
            if not self.draft_template.get(user_id) or not self.draft_targets.get(user_id):
                await self._edit(query.message, '请先选择模板和目标。', self._home_keyboard())
                return
            self.waiting[user_id] = 'task_rule'
            rendered = await self._edit(query.message, self._rule_text(), self._rule_examples_keyboard())
            self._remember_state_message(user_id, rendered)
            return

        if action.startswith('rule:'):
            if not self.draft_template.get(user_id) or not self.draft_targets.get(user_id):
                await self._edit(query.message, '请先选择模板和目标。', self._home_keyboard())
                return
            await self._create_task_edit(query.message, user_id, action.split(':', 1)[1])
            return

        if action.startswith('template:'):
            await self._edit(query.message, *(await self._template_detail_view(user_id, int(action.split(':', 1)[1]))))
            return

        if action.startswith('preview:'):
            template_id = int(action.split(':', 1)[1])
            try:
                await self.preview.preview_to_owner(user_id, template_id)
                await self._edit(query.message, '预览已发送。', self._after_preview_keyboard(template_id))
            except Exception as e:
                await self._edit(query.message, f'预览失败：{e}', self._home_keyboard())
            return

        if action.startswith('edit_template:'):
            template_id = int(action.split(':', 1)[1])
            self.waiting[user_id] = 'edit_template'
            self.editing_template[user_id] = template_id
            rendered = await self._edit(query.message, f'编辑模板 #{template_id}\n\n发送新的文字内容。\n\n说明：媒体模板暂时只能删除后重新保存。', self._back_keyboard(f'template:{template_id}'))
            self._remember_state_message(user_id, rendered)
            return

        if action.startswith('delete_template:'):
            template_id = int(action.split(':', 1)[1])
            await self._edit(query.message, f'确认删除模板 #{template_id}？', self._confirm_keyboard(f'confirm_delete_template:{template_id}', f'template:{template_id}'))
            return

        if action.startswith('confirm_delete_template:'):
            template_id = int(action.split(':', 1)[1])
            try:
                await self.templates.delete(user_id, template_id)
                await self._edit(query.message, f'模板 #{template_id} 已删除。', self._home_keyboard())
            except Exception as e:
                await self._edit(query.message, f'删除失败：{e}', self._home_keyboard())
            return

        if action.startswith('target:'):
            await self._edit(query.message, *(await self._target_detail_view(user_id, int(action.split(':', 1)[1]))))
            return

        if action.startswith('edit_target:'):
            target_id = int(action.split(':', 1)[1])
            self.waiting[user_id] = 'edit_target'
            self.editing_target[user_id] = target_id
            rendered = await self._edit(query.message, f'编辑目标 #{target_id}\n\n发送新的 @用户名 或 t.me 链接。', self._back_keyboard(f'target:{target_id}'))
            self._remember_state_message(user_id, rendered)
            return

        if action.startswith('delete_target:'):
            target_id = int(action.split(':', 1)[1])
            await self._edit(query.message, f'确认删除目标 #{target_id}？', self._confirm_keyboard(f'confirm_delete_target:{target_id}', f'target:{target_id}'))
            return

        if action.startswith('confirm_delete_target:'):
            target_id = int(action.split(':', 1)[1])
            try:
                await self.targets.delete_target(user_id, target_id)
                await self._edit(query.message, f'目标 #{target_id} 已删除。', self._home_keyboard())
            except Exception as e:
                await self._edit(query.message, f'删除失败：{e}', self._home_keyboard())
            return

    async def _add_target_message(self, message: Message, user_id: int, text: str) -> None:
        if not text:
            await message.reply_text('请发送 @用户名 或 t.me 链接。', reply_markup=self._back_keyboard())
            return
        try:
            target = await self.targets.add_target(user_id, text)
            self.waiting.pop(user_id, None)
            await self._edit_state_message(message, user_id, self._target_saved_text(target), self._target_saved_keyboard(target.id))
        except Exception as e:
            await self._edit_state_message(message, user_id, f'添加目标失败：{e}', self._back_keyboard())

    async def _edit_target_message(self, message: Message, user_id: int, text: str) -> None:
        target_id = self.editing_target.get(user_id)
        if not target_id:
            await message.reply_text('编辑状态已失效。', reply_markup=self._home_keyboard())
            return
        try:
            target = await self.targets.update_target(user_id, target_id, text)
            self.waiting.pop(user_id, None)
            self.editing_target.pop(user_id, None)
            await self._edit_state_message(message, user_id, self._target_saved_text(target), self._target_saved_keyboard(target.id))
        except Exception as e:
            await self._edit_state_message(message, user_id, f'更新目标失败：{e}', self._back_keyboard(f'target:{target_id}'))

    async def _save_template_message(self, message: Message, user_id: int) -> None:
        template = await self.templates.save_from_message(user_id, message)
        self.waiting.pop(user_id, None)
        await self._edit_state_message(
            message,
            user_id,
            f'消息模板 #{template.id} 已保存。\n\n先预览一遍，确认无误后再创建定时任务。',
            self._template_saved_keyboard(template.id),
        )

    async def _edit_template_message(self, message: Message, user_id: int, text: str) -> None:
        template_id = self.editing_template.get(user_id)
        if not template_id:
            await message.reply_text('编辑状态已失效。', reply_markup=self._home_keyboard())
            return
        if not text:
            await message.reply_text('目前只支持把模板编辑为文字内容。媒体模板请删除后重新保存。', reply_markup=self._back_keyboard(f'template:{template_id}'))
            return
        try:
            template = await self.templates.update_text(user_id, template_id, text)
            self.waiting.pop(user_id, None)
            self.editing_template.pop(user_id, None)
            await self._edit_state_message(message, user_id, f'模板 #{template.id} 已更新。', self._template_saved_keyboard(template.id))
        except Exception as e:
            await self._edit_state_message(message, user_id, f'更新模板失败：{e}', self._back_keyboard(f'template:{template_id}'))

    async def _start_task(self, message: Message, user_id: int) -> None:
        templates = await self.templates.list_recent(user_id, 10)
        targets = await self.targets.list_targets(user_id)
        if not templates:
            await self._edit(message, '还没有模板。先点击「保存群发内容」。', self._home_keyboard())
            return
        if not targets:
            await self._edit(message, '还没有目标。先点击「添加目标」。', self._home_keyboard())
            return
        self.draft_template.pop(user_id, None)
        self.draft_targets[user_id] = []
        text = '创建任务 · 选择模板\n\n点一个模板继续。'
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(self._template_button_text(t), callback_data=f'pick_template:{t.id}')] for t in templates[:10]]
            + [[InlineKeyboardButton('返回首页', callback_data='home')]]
        )
        await self._edit(message, text, keyboard)

    async def _create_task_reply(self, message: Message, user_id: int, rule_text: str) -> None:
        try:
            task = await self.tasks.create_task_from_text(user_id, self.draft_template[user_id], self.draft_targets[user_id], rule_text)
            self._clear_state(user_id)
            await self._edit_state_message(message, user_id, self._task_created_text(task), self._task_created_keyboard())
        except Exception as e:
            await self._edit_state_message(message, user_id, f'创建任务失败：{e}', self._rule_examples_keyboard())

    async def _create_task_edit(self, message: Message, user_id: int, rule_text: str) -> None:
        try:
            task = await self.tasks.create_task_from_text(user_id, self.draft_template[user_id], self.draft_targets[user_id], rule_text)
            self._clear_state(user_id)
            await self._edit(message, self._task_created_text(task), self._task_created_keyboard())
        except Exception as e:
            await self._edit(message, f'创建任务失败：{e}', self._rule_examples_keyboard())

    async def _edit_task_rule_reply(self, message: Message, user_id: int, rule_text: str) -> None:
        task_id = self.editing_task.get(user_id)
        if not task_id:
            await message.reply_text('编辑状态已失效。', reply_markup=self._home_keyboard())
            return
        try:
            task = await self.tasks.update_rule(user_id, task_id, rule_text)
            self._clear_state(user_id)
            await self._edit_state_message(message, user_id, self._task_updated_text(task), self._task_detail_keyboard(task))
        except Exception as e:
            await self._edit_state_message(message, user_id, f'修改失败：{e}', self._rule_examples_keyboard(prefix=f'update_rule:{task_id}:', back_to=f'task:{task_id}'))

    def _custody_notice_text(self) -> str:
        return (
            '信鸽账号托管须知\n\n'
            '信鸽是 TBaaS 旗下产品，用来连接你的 Telegram 账号，并按你设置的目标、模板和时间自动发送消息。\n\n'
            '使用前请了解：\n\n'
            '1. 登录后，信鸽会保存一份加密的 Telegram 登录状态，用来执行你创建的发送任务。\n'
            '2. 信鸽不会保存你的验证码或 2FA 密码；这些信息只用于当次登录。\n'
            '3. 你可以随时在信鸽里断开账号，也可以在 Telegram 设置 → 设备 中移除这次登录。\n'
            '4. 频繁发送消息可能触发 Telegram 风控，请只向你有权限联系或管理的目标发送。\n\n'
            '官方频道：@TBaaS_cc'
        )

    async def _home_view(self, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        session = await self.account_sessions.get_session(user_id)
        if session and session.status == 'connected':
            status = f'已连接账号：{session.display_name or session.phone or "Telegram 账号"}'
        elif session and session.status == 'blocked':
            status = f'账号连接不可用：{session.last_error or "服务端未配置"}'
        else:
            status = '未连接 Telegram 账号'
        return (
            '信鸽，你最得力的账号托管助手\n\n'
            f'{status}\n\n'
            '三步开始：\n'
            '1. 连接 Telegram 账号\n'
            '2. 保存目标和群发内容\n'
            '3. 创建自动发送任务',
            self._home_keyboard(bool(session and session.status == 'connected')),
        )

    async def _targets_view(self, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        targets = await self.targets.list_targets(user_id)
        text = '目标管理\n\n' + ('暂无目标。' if not targets else '点击目标可编辑或删除。')
        buttons = [[InlineKeyboardButton(self._target_button_text(t), callback_data=f'target:{t.id}')] for t in targets[: self.PAGE_SIZE]]
        buttons += [[InlineKeyboardButton('添加目标', callback_data='add_target')], [InlineKeyboardButton('返回首页', callback_data='home')]]
        return text, InlineKeyboardMarkup(buttons)

    async def _target_detail_view(self, user_id: int, target_id: int) -> tuple[str, InlineKeyboardMarkup]:
        target = await self.targets.targets.get(target_id)
        if not target or target.owner_user_id != user_id:
            return '目标不存在。', self._home_keyboard()
        text = (
            f'目标 #{target.id}\n\n'
            f'{target.target_input}\n'
            f'状态：{self._status_text(target.status)}\n'
            f'类型：{target.target_type or "-"}\n'
            f'标题：{target.target_title or "-"}\n'
            f'说明：{target.last_error or "可用于发送任务"}'
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('编辑', callback_data=f'edit_target:{target.id}'), InlineKeyboardButton('删除', callback_data=f'delete_target:{target.id}')],
            [InlineKeyboardButton('返回目标列表', callback_data='targets'), InlineKeyboardButton('首页', callback_data='home')],
        ])
        return text, keyboard

    async def _templates_view(self, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        templates = await self.templates.list_recent(user_id, 10)
        text = '模板管理\n\n' + ('暂无模板。' if not templates else '点击模板可预览、编辑或删除。')
        buttons = [[InlineKeyboardButton(self._template_button_text(t), callback_data=f'template:{t.id}')] for t in templates[: self.PAGE_SIZE]]
        buttons += [[InlineKeyboardButton('保存群发内容', callback_data='add_template')], [InlineKeyboardButton('返回首页', callback_data='home')]]
        return text, InlineKeyboardMarkup(buttons)

    async def _template_detail_view(self, user_id: int, template_id: int) -> tuple[str, InlineKeyboardMarkup]:
        template = await self.templates.repo.get(template_id)
        if not template or template.owner_user_id != user_id:
            return '模板不存在。', self._home_keyboard()
        text = f'模板 #{template.id}\n\n类型：{template.message_type}\n内容：{self._template_preview_text(template, 160)}'
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('预览', callback_data=f'preview:{template.id}'), InlineKeyboardButton('编辑文字', callback_data=f'edit_template:{template.id}')],
            [InlineKeyboardButton('删除', callback_data=f'delete_template:{template.id}')],
            [InlineKeyboardButton('返回模板列表', callback_data='templates'), InlineKeyboardButton('首页', callback_data='home')],
        ])
        return text, keyboard

    async def _tasks_view(self, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        tasks = await self.tasks.list_tasks(user_id)
        if not tasks:
            text = '任务列表\n\n暂无任务。'
            buttons = []
        else:
            text = '任务列表\n\n点击任务可暂停、修改规则或删除。'
            buttons = [[InlineKeyboardButton(self._task_button_text(task), callback_data=f'task:{task.id}')] for task in tasks[:10]]
        buttons += [[InlineKeyboardButton('创建定时任务', callback_data='newtask')], [InlineKeyboardButton('返回首页', callback_data='home')]]
        return text, InlineKeyboardMarkup(buttons)

    async def _task_detail_view(self, user_id: int, task_id: int) -> tuple[str, InlineKeyboardMarkup]:
        try:
            task = await self.tasks.get_task(user_id, task_id)
        except Exception:
            return '任务不存在。', self._home_keyboard()
        text = (
            f'任务 #{task.id}\n\n'
            f'状态：{self._task_status_text(task.status)}\n'
            f'模板：#{task.template_id}\n'
            f'目标数：{len(task.target_ids)}\n'
            f'发送规则：{self.tasks.time_parser.describe_rule(task.schedule_rule)}\n'
            f'下次发送：{self.tasks.time_parser.format_dt(task.next_run_at, task.timezone)}'
        )
        return text, self._task_detail_keyboard(task)

    async def _pick_targets_view(self, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        targets = await self.targets.list_targets(user_id)
        selected = set(self.draft_targets.get(user_id, []))
        buttons = []
        for target in targets[:10]:
            mark = '' if target.id in selected else ''
            buttons.append([InlineKeyboardButton(mark + self._target_button_text(target), callback_data=f'toggle_target:{target.id}')])
        if selected:
            buttons.append([InlineKeyboardButton('下一步：选择发送规则', callback_data='task_rule')])
        buttons.append([InlineKeyboardButton('返回首页', callback_data='home')])
        return '创建任务 · 选择目标\n\n可选择多个目标。', InlineKeyboardMarkup(buttons)

    async def _edit(self, message: Message, text: str, keyboard: InlineKeyboardMarkup | None = None) -> Message | None:
        try:
            return await message.edit_text(text, reply_markup=keyboard)
        except Exception:
            return await message.reply_text(text, reply_markup=keyboard)

    async def _edit_state_message(self, message: Message, user_id: int, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
        message_id = self.state_message_id.pop(user_id, None)
        if not message_id:
            await message.reply_text(text, reply_markup=keyboard)
            return
        try:
            await message.get_bot().edit_message_text(chat_id=message.chat_id, message_id=message_id, text=text, reply_markup=keyboard)
        except Exception:
            await message.reply_text(text, reply_markup=keyboard)

    def _remember_state_message(self, user_id: int, message: Message | None) -> None:
        if message:
            self.state_message_id[user_id] = message.message_id

    def _clear_state(self, user_id: int) -> None:
        self.waiting.pop(user_id, None)
        self.editing_target.pop(user_id, None)
        self.editing_template.pop(user_id, None)
        self.draft_template.pop(user_id, None)
        self.draft_targets.pop(user_id, None)
        self.editing_task.pop(user_id, None)
        self.state_message_id.pop(user_id, None)

    def _home_keyboard(self, connected: bool = False) -> InlineKeyboardMarkup:
        return home_keyboard(connected=connected)

    def _login_method_keyboard(self) -> InlineKeyboardMarkup:
        return login_method_keyboard()

    def _qr_login_keyboard(self) -> InlineKeyboardMarkup:
        return qr_login_keyboard()

    def _template_saved_keyboard(self, template_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('预览', callback_data=f'preview:{template_id}'), InlineKeyboardButton('编辑', callback_data=f'edit_template:{template_id}')],
            [InlineKeyboardButton('创建任务', callback_data='newtask'), InlineKeyboardButton('模板管理', callback_data='templates')],
            [InlineKeyboardButton('首页', callback_data='home')],
        ])

    def _target_saved_keyboard(self, target_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('编辑', callback_data=f'edit_target:{target_id}'), InlineKeyboardButton('删除', callback_data=f'delete_target:{target_id}')],
            [InlineKeyboardButton('创建任务', callback_data='newtask'), InlineKeyboardButton('目标管理', callback_data='targets')],
            [InlineKeyboardButton('首页', callback_data='home')],
        ])

    def _after_preview_keyboard(self, template_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('创建任务', callback_data='newtask'), InlineKeyboardButton('编辑模板', callback_data=f'edit_template:{template_id}')],
            [InlineKeyboardButton('模板管理', callback_data='templates'), InlineKeyboardButton('首页', callback_data='home')],
        ])

    def _task_created_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('查看任务', callback_data='tasks')],
            [InlineKeyboardButton('添加目标', callback_data='add_target'), InlineKeyboardButton('保存内容', callback_data='add_template')],
            [InlineKeyboardButton('首页', callback_data='home')],
        ])

    def _task_detail_keyboard(self, task) -> InlineKeyboardMarkup:
        status_button = InlineKeyboardButton('恢复', callback_data=f'resume_task:{task.id}') if task.status == 'paused' else InlineKeyboardButton('暂停', callback_data=f'pause_task:{task.id}')
        return InlineKeyboardMarkup([
            [status_button, InlineKeyboardButton('修改规则', callback_data=f'edit_task_rule:{task.id}')],
            [InlineKeyboardButton('删除', callback_data=f'delete_task:{task.id}')],
            [InlineKeyboardButton('返回任务列表', callback_data='tasks'), InlineKeyboardButton('首页', callback_data='home')],
        ])

    def _back_keyboard(self, back_to: str = 'home') -> InlineKeyboardMarkup:
        return back_keyboard(back_to)

    def _confirm_keyboard(self, confirm_action: str, cancel_action: str) -> InlineKeyboardMarkup:
        return confirm_keyboard(confirm_action, cancel_action)

    def _rule_examples_keyboard(self, prefix: str = 'rule:', back_to: str = 'home') -> InlineKeyboardMarkup:
        return rule_examples_keyboard(prefix, back_to)

    def _rule_text(self) -> str:
        return (
            '创建任务 · 选择发送规则\n\n'
            '直接点下面的规则，也可以自己发送一条：\n'
            '• 单次10分钟后\n'
            '• 单次2026-06-02 10:00\n'
            '• 每天10:00\n'
            '• 每天10:00 18:00\n'
            '• 每10分钟\n'
            '• 每2小时\n\n'
            '时间按 Asia/Shanghai 处理'
        )

    def _connect_account_text(self, session) -> str:
        if session.status == 'blocked':
            return (
                '连接账号暂不可用。\n\n'
                f'{session.last_error}\n\n'
                '下一步需要在服务端配置 Telegram API ID/API Hash，并接入 TDLib/Telethon 登录流程。'
            )
        return (
            '账号托管 QR 登录\n\n'
            'QR 登录本质是登录一个新的 Telegram 客户端设备。\n'
            '我们不会接收你的密码或验证码，但登录成功后服务端会持有加密 session，用于按任务自动发送。\n\n'
            '安全措施：session 加密保存；可随时断开账号；公开关键代码后重点公开登录态保存和发送边界。'
        )

    def _make_qr_image(self, user_id: int, qr_url: str) -> Path:
        path = Path(tempfile.gettempdir()) / f'xinge_qr_{user_id}.png'
        img = qrcode.make(qr_url)
        img.save(path)
        return path

    def _target_saved_text(self, target) -> str:
        return (
            f'目标 #{target.id} 已保存。\n\n'
            f'{target.target_input}\n'
            f'状态：{self._status_text(target.status)}\n'
            f'{target.last_error or "可用于发送任务"}'
        )

    def _task_created_text(self, task) -> str:
        return (
            f'任务 #{task.id} 已创建。\n\n'
            f'模板：#{task.template_id}\n'
            f'目标数：{len(task.target_ids)}\n'
            f'发送规则：{self.tasks.time_parser.describe_rule(task.schedule_rule)}\n'
            f'下次发送：{self.tasks.time_parser.format_dt(task.next_run_at, task.timezone)}\n\n'
            f'只有状态为「可发送」的目标会被实际发送。'
        )

    def _task_updated_text(self, task) -> str:
        return (
            f'任务 #{task.id} 已更新。\n\n'
            f'发送规则：{self.tasks.time_parser.describe_rule(task.schedule_rule)}\n'
            f'下次发送：{self.tasks.time_parser.format_dt(task.next_run_at, task.timezone)}\n'
            f'状态：{self._task_status_text(task.status)}'
        )

    def _task_button_text(self, task) -> str:
        return f'#{task.id} · {self._task_status_text(task.status)} · {self.tasks.time_parser.describe_rule(task.schedule_rule)} · 下次 {self.tasks.time_parser.format_dt(task.next_run_at, task.timezone)}'

    def _template_button_text(self, template) -> str:
        return f'#{template.id} {template.message_type} · {self._template_preview_text(template, 32)}'

    def _template_preview_text(self, template, limit: int) -> str:
        preview = (template.text or template.caption or '媒体消息').replace('\n', ' ')
        return preview[:limit] or '空内容'

    def _target_button_text(self, target) -> str:
        return f'#{target.id} {target.target_input} · {self._status_text(target.status)}'

    def _status_text(self, status: str) -> str:
        return {
            'sendable': '可发送',
            'invalid': '无效',
            'pending': '待账号解析',
        }.get(status, status)

    def _task_status_text(self, status: str) -> str:
        return {
            'active': '运行中',
            'paused': '已暂停',
            'completed': '已完成',
        }.get(status, status)
