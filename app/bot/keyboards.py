from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def home_keyboard(*, connected: bool) -> InlineKeyboardMarkup:
    account_row = [InlineKeyboardButton('断开账号', callback_data='disconnect_account')] if connected else [InlineKeyboardButton('连接账号', callback_data='connect_account')]
    return InlineKeyboardMarkup([
        account_row,
        [InlineKeyboardButton('添加目标', callback_data='add_target'), InlineKeyboardButton('保存群发内容', callback_data='add_template')],
        [InlineKeyboardButton('创建定时任务', callback_data='newtask')],
        [InlineKeyboardButton('目标管理', callback_data='targets'), InlineKeyboardButton('模板管理', callback_data='templates')],
        [InlineKeyboardButton('任务列表', callback_data='tasks')],
    ])


def login_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('双设备扫码登录', callback_data='qr_login')],
        [InlineKeyboardButton('单设备手机号登录', callback_data='phone_login')],
        [InlineKeyboardButton('返回首页', callback_data='home')],
    ])


def phone_login_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('打开登录页', web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton('返回首页', callback_data='home')],
    ])


def qr_login_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('我已确认登录', callback_data='confirm_qr_login')],
        [InlineKeyboardButton('重新生成二维码', callback_data='connect_account')],
        [InlineKeyboardButton('返回首页', callback_data='home')],
    ])


def back_keyboard(back_to: str = 'home') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton('返回', callback_data=back_to)]])


def confirm_keyboard(confirm_action: str, cancel_action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('确认删除', callback_data=confirm_action)],
        [InlineKeyboardButton('取消', callback_data=cancel_action)],
    ])


def rule_examples_keyboard(prefix: str = 'rule:', back_to: str = 'home') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('单次10分钟后', callback_data=f'{prefix}单次10分钟后'), InlineKeyboardButton('单次1小时后', callback_data=f'{prefix}单次1小时后')],
        [InlineKeyboardButton('每天10:00', callback_data=f'{prefix}每天10:00'), InlineKeyboardButton('每天10:00 18:00', callback_data=f'{prefix}每天10:00 18:00')],
        [InlineKeyboardButton('每10分钟', callback_data=f'{prefix}每10分钟'), InlineKeyboardButton('每2小时', callback_data=f'{prefix}每2小时')],
        [InlineKeyboardButton('返回', callback_data=back_to)],
    ])
