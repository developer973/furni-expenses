"""
Admin commands for the manager/owner of the system
Only accessible by ADMIN_TELEGRAM_IDS from config.py
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sheets_manager import SheetsManager
from config import Config

sheets = SheetsManager()


def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_TELEGRAM_IDS


async def admin_add_engineer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_engineer <telegram_id> <name> <project> <deposit> [currency]
    Example: /add_engineer 987654321 "Ivan Petrov" "Project Alpha" 5000 AED
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Использование:\n"
            "`/add_engineer <telegram_id> <имя> <проект> <депозит> [валюта]`\n\n"
            "Пример:\n"
            "`/add_engineer 987654321 Иван_Петров Проект_А 5000 AED`",
            parse_mode="Markdown"
        )
        return

    telegram_id = args[0]
    name = args[1].replace("_", " ")
    project = args[2].replace("_", " ")
    deposit = float(args[3])
    currency = args[4] if len(args) > 4 else Config.DEFAULT_CURRENCY

    success = sheets.add_engineer(telegram_id, name, project, deposit, currency)
    
    if success:
        await update.message.reply_text(
            f"✅ Инженер добавлен!\n\n"
            f"👤 {name}\n"
            f"🏗 Проект: {project}\n"
            f"💰 Депозит: {deposit:,.2f} {currency}\n"
            f"🆔 Telegram ID: `{telegram_id}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Инженер уже существует или ошибка.")


async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /topup <telegram_id> <amount>
    Add funds to engineer's account
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: `/topup <telegram_id> <сумма>`\n"
            "Пример: `/topup 987654321 2000`",
            parse_mode="Markdown"
        )
        return

    telegram_id = args[0]
    amount = float(args[1])
    
    engineer = sheets.get_engineer(telegram_id)
    if not engineer:
        await update.message.reply_text("❌ Инженер не найден.")
        return
    
    new_balance = sheets.top_up_balance(telegram_id, amount)
    currency = engineer.get("currency", Config.DEFAULT_CURRENCY)
    
    await update.message.reply_text(
        f"✅ Депозит пополнен!\n\n"
        f"👤 {engineer.get('name')}\n"
        f"➕ Добавлено: {amount:,.2f} {currency}\n"
        f"💰 Новый баланс: *{new_balance:,.2f} {currency}*",
        parse_mode="Markdown"
    )


async def admin_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /overview — Show all engineers and their balances
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return
    
    engineers = sheets.get_all_engineers()
    if not engineers:
        await update.message.reply_text("📭 Нет зарегистрированных инженеров.")
        return
    
    lines = ["👥 *Все инженеры и балансы:*\n"]
    for eng in engineers:
        balance = float(eng.get("balance", 0))
        initial = float(eng.get("initial_deposit", 0))
        currency = eng.get("currency", "AED")
        spent_pct = ((initial - balance) / initial * 100) if initial > 0 else 0
        
        icon = "🟢" if balance > Config.LOW_BALANCE_THRESHOLD else "🔴"
        lines.append(
            f"{icon} *{eng.get('name')}*\n"
            f"   📁 {eng.get('project', '—')}\n"
            f"   💰 {balance:,.0f} / {initial:,.0f} {currency} ({100-spent_pct:.0f}% осталось)"
        )
    
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /report — Show last 10 transactions across all engineers
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return
    
    transactions = sheets.get_transactions(limit=10)
    
    if not transactions:
        await update.message.reply_text("📭 Нет транзакций.")
        return
    
    lines = ["📋 *Последние 10 транзакций:*\n"]
    for t in transactions:
        date = str(t.get("date", ""))[:10]
        amount = float(t.get("amount", 0))
        currency = t.get("currency", "AED")
        name = t.get("engineer_name", "—")
        vendor = t.get("vendor", "—")
        lines.append(f"📅 {date} | 👤 {name} | 💰 {amount:,.0f} {currency} | 🏪 {vendor}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# Register admin handlers — call this from bot.py
def register_admin_handlers(app):
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("add_engineer", admin_add_engineer))
    app.add_handler(CommandHandler("topup", admin_topup))
    app.add_handler(CommandHandler("overview", admin_overview))
    app.add_handler(CommandHandler("report", admin_report))
