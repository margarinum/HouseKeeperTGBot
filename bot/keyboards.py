from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

VERIFY_BTN = "Верифицироваться"
DELETE_VERIFY_BTN = "Удалить верификацию"
ADMIN_BTN = "Админ-панель"
CANCEL_BTN = "Отмена"
DOCS_BTN = "Документация"
FAQ_BTN = "Ответы на частые вопросы"
AI_BTN = "❓ Задать вопрос"


def main_menu(is_verified: bool, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if is_verified:
        rows.append([KeyboardButton(text=DELETE_VERIFY_BTN)])
    else:
        rows.append([KeyboardButton(text=VERIFY_BTN)])
    if is_verified:
        rows.append([KeyboardButton(text=DOCS_BTN)])
        rows.append([KeyboardButton(text=AI_BTN)])
    rows.append([KeyboardButton(text=FAQ_BTN)])
    if is_admin:
        rows.append([KeyboardButton(text=ADMIN_BTN)])
    rows.append([KeyboardButton(text=CANCEL_BTN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="Управление документацией", callback_data="admin:docs")],
        [InlineKeyboardButton(text="Ответы на частые вопросы", callback_data="admin:faq")],
        [InlineKeyboardButton(text="Неверифицированные", callback_data="admin:unverified_actions")],
        [InlineKeyboardButton(text="Верифицированные", callback_data="admin:verified_actions")],
        [InlineKeyboardButton(text="Оплатившие", callback_data="admin:paid_actions")],
        [InlineKeyboardButton(text="Шлагбаумы", callback_data="admin:barriers")],
        [InlineKeyboardButton(text="Синхронизировать участников с группой", callback_data="admin:sync_table")],
        [InlineKeyboardButton(text="Снять лимит регистрации на квартиру", callback_data="verified:remove_limit")],
        [InlineKeyboardButton(text="Администраторы", callback_data="admin:list_admins")],
        [
            InlineKeyboardButton(text="Добавить администратора", callback_data="admin:add_admin"),
            InlineKeyboardButton(text="Удалить администратора", callback_data="admin:remove_admin"),
        ],
    ])


def unverified_actions_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать неверифицированных", callback_data="admin:unverified")],
        [InlineKeyboardButton(text="Предупредить", callback_data="admin:warn")],
        [InlineKeyboardButton(text="Ограничить отправку", callback_data="admin:restrict_unverified")],
        [InlineKeyboardButton(text="Отменить ограничение отправки", callback_data="admin:unrestrict_unverified")],
        [InlineKeyboardButton(text="Удалить", callback_data="admin:purge")],
        [InlineKeyboardButton(text="Обнулить счетчик верификаций", callback_data="admin:reset_attempts")],
        [InlineKeyboardButton(text="Ручная верификация", callback_data="admin:manual_verify")],
        [InlineKeyboardButton(text="Экспорт неверифицированных", callback_data="admin:export_unverified")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:back")],
    ])


def verified_actions_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Снять верификацию", callback_data="admin:revoke_verification")],
        [InlineKeyboardButton(text="Экспорт верифицированных", callback_data="admin:export_verified")],
        [InlineKeyboardButton(text="Отправить сообщение", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="Создать голосование", callback_data="admin:create_poll")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:back")],
    ])


def paid_actions_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Экспорт оплативших", callback_data="paid:export")],
        [InlineKeyboardButton(text="Отправить сообщение", callback_data="paid:broadcast")],
        [InlineKeyboardButton(text="Создать голосование", callback_data="paid:create_poll")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:back")],
    ])


def barriers_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5к2", callback_data="barrier:open:5k2")],
        [InlineKeyboardButton(text="3к4 (север)", callback_data="barrier:open:3k4_north")],
        [InlineKeyboardButton(text="3к4 (юг)", callback_data="barrier:open:3k4_south")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:back")],
    ])


def confirm_revoke_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=f"admin:revoke_confirm:{user_id}"),
            InlineKeyboardButton(text="Нет", callback_data="admin:revoke_cancel"),
        ]
    ])
    
def houses_menu(houses: list[str]) -> ReplyKeyboardMarkup:
    rows = []

    for house in houses:
        rows.append([KeyboardButton(text=house)])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
    )


def poll_vote_keyboard(poll_id: int, options: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for opt in options:
        rows.append([InlineKeyboardButton(
            text=opt["option_text"],
            callback_data=f"vote:{poll_id}:{opt['option_id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def poll_manage_keyboard(poll_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Результаты", callback_data=f"poll:results:{poll_id}")],
        [InlineKeyboardButton(text="🔒 Закрыть голосование", callback_data=f"poll:close:{poll_id}")],
    ])


def docs_keyboard(docs: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Добавить документ", callback_data="docs:add")]]
    for doc in docs:
        rows.append([InlineKeyboardButton(
            text=f"🗑 {doc['name']}",
            callback_data=f"docs:delete:{doc['doc_id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_docs_keyboard(docs: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for doc in docs:
        rows.append([InlineKeyboardButton(
            text=doc["name"],
            callback_data=f"docs:get:{doc['doc_id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Шлагбаум", callback_data="faq:edit:barrier")],
        [InlineKeyboardButton(text="🤖 Бот", callback_data="faq:edit:bot")],
    ])


def faq_user_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Шлагбаум", callback_data="faq:get:barrier")],
        [InlineKeyboardButton(text="🤖 Бот", callback_data="faq:get:bot")],
    ])


def ai_conversation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Продолжить разговор", callback_data="ai:continue"),
            InlineKeyboardButton(text="Завершить разговор", callback_data="ai:end"),
        ],
    ])
