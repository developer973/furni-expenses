"""
Expense Tracker Bot for Lead Engineers
Reads receipts via Claude Vision, deducts from engineer deposits, syncs to Google Sheets
"""

import os
import logging
import base64
import json
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from sheets_manager import SheetsManager
from config import Config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

sheets = SheetsManager()

# ─── CLAUDE VISION: Read receipt ─────────────────────────────────────────────

async def read_receipt_with_claude(image_bytes: bytes) -> dict:
    """Send receipt image to Claude API and extract expense data."""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    
    headers = {
        "x-api-key": Config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    
    payload = {
        "model": "claude-opus-4-5",
        "max_tokens": 512,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Ты помощник по распознаванию чеков. "
                        "Извлеки из этого чека следующую информацию и верни ТОЛЬКО JSON без пояснений:\n"
                        "{\n"
                        '  "amount": <сумма числом, только цифры и точка>,\n'
                        '  "currency": "<валюта, например AED, USD, RUB>",\n'
                        '  "vendor": "<название магазина/поставщика>",\n'
                        '  "category": "<одно из: transport, purchase, components, other>",\n'
                        '  "date": "<дата в формате YYYY-MM-DD или null если не видно>",\n'
                        '  "description": "<краткое описание покупки>",\n'
                        '  "confidence": <от 0.0 до 1.0 насколько ты уверен в сумме>\n'
                        "}"
                    ),
                }
            ],
        }],
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    
    text = data["content"][0]["text"].strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    
    return json.loads(text)


# ─── COMMAND HANDLERS ────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and registration check."""
    user_id = str(update.effective_user.id)
    engineer = sheets.get_engineer(user_id)
    
    if engineer:
        balance = engineer.get("balance", 0)
        name = engineer.get("name", "Инженер")
        await update.message.reply_text(
            f"👋 Привет, {name}!\n\n"
            f"💰 Твой текущий баланс: *{balance:,.2f} {engineer.get('currency','AED')}*\n\n"
            f"📸 Отправь фото чека — я автоматически распознаю сумму и спишу с баланса.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "👋 Привет!\n\n"
            "❌ Ты не зарегистрирован в системе.\n"
            "Обратись к руководителю чтобы тебя добавили в систему учёта расходов."
        )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current balance."""
    user_id = str(update.effective_user.id)
    engineer = sheets.get_engineer(user_id)
    
    if not engineer:
        await update.message.reply_text("❌ Ты не зарегистрирован в системе.")
        return
    
    total_spent = sheets.get_total_spent(user_id)
    initial = engineer.get("initial_deposit", 0)
    current = engineer.get("balance", 0)
    currency = engineer.get("currency", "AED")
    
    await update.message.reply_text(
        f"💼 *Твой баланс*\n\n"
        f"Начальный депозит: {initial:,.2f} {currency}\n"
        f"Потрачено: {total_spent:,.2f} {currency}\n"
        f"─────────────────\n"
        f"Остаток: *{current:,.2f} {currency}*",
        parse_mode="Markdown"
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show last 5 transactions."""
    user_id = str(update.effective_user.id)
    engineer = sheets.get_engineer(user_id)
    
    if not engineer:
        await update.message.reply_text("❌ Ты не зарегистрирован в системе.")
        return
    
    transactions = sheets.get_transactions(user_id, limit=5)
    
    if not transactions:
        await update.message.reply_text("📭 У тебя пока нет расходов.")
        return
    
    currency = engineer.get("currency", "AED")
    lines = ["📋 *Последние расходы:*\n"]
    for t in transactions:
        date = t.get("date", "")[:10]
        amount = float(t.get("amount", 0))
        vendor = t.get("vendor", "—")
        category_map = {
            "transport": "🚗", "purchase": "🛒", 
            "components": "⚙️", "other": "📦"
        }
        icon = category_map.get(t.get("category", "other"), "📦")
        lines.append(f"{icon} {date} — *{amount:,.2f} {currency}* — {vendor}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── RECEIPT PHOTO HANDLER ────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process receipt photo: read with Claude, confirm, deduct."""
    user_id = str(update.effective_user.id)
    engineer = sheets.get_engineer(user_id)
    
    if not engineer:
        await update.message.reply_text("❌ Ты не зарегистрирован в системе.")
        return
    
    # Show processing message
    msg = await update.message.reply_text("🔍 Читаю чек...")
    
    try:
        # Download photo (highest resolution)
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        
        # Extract receipt data via Claude
        receipt = await read_receipt_with_claude(bytes(image_bytes))
        
        amount = float(receipt.get("amount", 0))
        currency = receipt.get("currency", engineer.get("currency", "AED"))
        vendor = receipt.get("vendor", "Неизвестно")
        category = receipt.get("category", "other")
        date = receipt.get("date") or datetime.now().strftime("%Y-%m-%d")
        description = receipt.get("description", "")
        confidence = float(receipt.get("confidence", 0.5))
        
        if amount <= 0:
            await msg.edit_text("❌ Не удалось распознать сумму. Попробуй отправить более чёткое фото.")
            return
        
        current_balance = float(engineer.get("balance", 0))
        new_balance = current_balance - amount
        
        category_map = {
            "transport": "🚗 Транспорт",
            "purchase": "🛒 Закупка",
            "components": "⚙️ Комплектующие",
            "other": "📦 Другое"
        }
        cat_label = category_map.get(category, "📦 Другое")
        
        confidence_icon = "✅" if confidence >= 0.8 else "⚠️"
        
        # Store pending transaction in context
        context.user_data["pending_receipt"] = {
            "user_id": user_id,
            "engineer_name": engineer.get("name"),
            "amount": amount,
            "currency": currency,
            "vendor": vendor,
            "category": category,
            "date": date,
            "description": description,
            "current_balance": current_balance,
            "new_balance": new_balance,
        }
        
        # Ask for confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_receipt"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_receipt"),
            ]
        ]
        
        await msg.edit_text(
            f"{confidence_icon} *Чек распознан*\n\n"
            f"🏪 Магазин: {vendor}\n"
            f"💰 Сумма: *{amount:,.2f} {currency}*\n"
            f"📁 Категория: {cat_label}\n"
            f"📅 Дата: {date}\n"
            f"📝 {description}\n\n"
            f"──────────────────\n"
            f"Баланс сейчас: {current_balance:,.2f} {currency}\n"
            f"Баланс после: *{new_balance:,.2f} {currency}*\n\n"
            f"Подтвердить списание?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Receipt processing error: {e}")
        await msg.edit_text(
            "❌ Ошибка при обработке чека. Попробуй ещё раз или напиши сумму вручную командой:\n"
            "`/manual 150.00 Название магазина`",
            parse_mode="Markdown"
        )


async def confirm_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt confirmation/cancellation."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_receipt":
        context.user_data.pop("pending_receipt", None)
        await query.edit_message_text("❌ Расход отменён.")
        return
    
    pending = context.user_data.get("pending_receipt")
    if not pending:
        await query.edit_message_text("❌ Данные не найдены. Попробуй заново.")
        return
    
    try:
        # Save to Google Sheets
        sheets.add_transaction(pending)
        sheets.update_balance(pending["user_id"], pending["new_balance"])
        
        context.user_data.pop("pending_receipt", None)
        
        currency = pending["currency"]
        await query.edit_message_text(
            f"✅ *Расход записан!*\n\n"
            f"💰 Списано: {pending['amount']:,.2f} {currency}\n"
            f"💼 Остаток: *{pending['new_balance']:,.2f} {currency}*",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error saving transaction: {e}")
        await query.edit_message_text("❌ Ошибка сохранения. Обратись к руководителю.")


async def manual_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add expense manually: /manual 150.50 Vendor Name"""
    user_id = str(update.effective_user.id)
    engineer = sheets.get_engineer(user_id)
    
    if not engineer:
        await update.message.reply_text("❌ Ты не зарегистрирован.")
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "Использование: `/manual <сумма> [название]`\n"
            "Пример: `/manual 150.50 Carrefour`",
            parse_mode="Markdown"
        )
        return
    
    try:
        amount = float(args[0])
        vendor = " ".join(args[1:]) if len(args) > 1 else "Ручной ввод"
    except ValueError:
        await update.message.reply_text("❌ Неверная сумма. Пример: `/manual 150.50`", parse_mode="Markdown")
        return
    
    current_balance = float(engineer.get("balance", 0))
    new_balance = current_balance - amount
    currency = engineer.get("currency", "AED")
    
    pending = {
        "user_id": user_id,
        "engineer_name": engineer.get("name"),
        "amount": amount,
        "currency": currency,
        "vendor": vendor,
        "category": "other",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "description": "Ручной ввод",
        "current_balance": current_balance,
        "new_balance": new_balance,
    }
    context.user_data["pending_receipt"] = pending
    
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_receipt"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_receipt"),
    ]]
    
    await update.message.reply_text(
        f"📝 *Ручной ввод расхода*\n\n"
        f"🏪 Магазин: {vendor}\n"
        f"💰 Сумма: *{amount:,.2f} {currency}*\n"
        f"Баланс после: *{new_balance:,.2f} {currency}*\n\n"
        f"Подтвердить?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def main():
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("manual", manual_expense))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(confirm_receipt_callback, pattern="^(confirm|cancel)_receipt$"))
    
    logger.info("🤖 Expense bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
