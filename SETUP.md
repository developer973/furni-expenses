# 🤖 Expense Tracker Bot — Руководство по запуску

## Что делает этот бот

- Инженер отправляет **фото чека** в Telegram
- Claude Vision **читает сумму, магазин, категорию**
- Показывает карточку подтверждения — инженер нажимает ✅
- **Сумма списывается** с его депозита
- Всё записывается в **Google Sheets** автоматически

---

## ШАГ 1 — Создать Telegram бота

1. Открой Telegram → найди **@BotFather**
2. Отправь `/newbot`
3. Дай имя и username боту
4. Скопируй токен (вида `7312456789:AAFxyz...`)

---

## ШАГ 2 — Получить Anthropic API ключ

1. Зайди на https://console.anthropic.com
2. API Keys → **Create Key**
3. Скопируй ключ (вида `sk-ant-api03-...`)

---

## ШАГ 3 — Настроить Google Sheets

### 3.1 Создать Google Sheets таблицу

1. Открой https://sheets.google.com
2. Создай новую таблицу
3. Скопируй **ID таблицы** из URL:
   ```
   https://docs.google.com/spreadsheets/d/ЭТОТ_ID_НУЖЕН/edit
   ```

### 3.2 Создать Service Account

1. Зайди на https://console.cloud.google.com
2. Создай новый проект или выбери существующий
3. **APIs & Services → Library** → включи:
   - `Google Sheets API`
   - `Google Drive API`
4. **APIs & Services → Credentials → Create Credentials → Service Account**
5. Дай имя, нажми Create
6. На странице Service Account → **Keys → Add Key → JSON**
7. Скачай файл, переименуй в `credentials.json`
8. Положи `credentials.json` в папку с ботом

### 3.3 Дать доступ к таблице

1. Открой скачанный `credentials.json`
2. Найди поле `"client_email"` — скопируй email
3. В Google Sheets → **Поделиться** → вставь этот email → **Редактор**

---

## ШАГ 4 — Узнать свой Telegram ID

1. Напиши боту **@userinfobot** в Telegram
2. Он покажет твой ID (число вида `123456789`)

---

## ШАГ 5 — Установить и запустить

### Установка зависимостей

```bash
cd expense_bot
pip install -r requirements.txt
```

### Настройка переменных окружения

Создай файл `.env` или экспортируй переменные:

```bash
export TELEGRAM_TOKEN="7312456789:AAFxyz..."
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export GOOGLE_CREDENTIALS_FILE="credentials.json"
export SPREADSHEET_ID="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
export ADMIN_IDS="123456789"   # твой Telegram ID
```

### Запуск

```bash
python bot.py
```

---

## ШАГ 6 — Добавить инженеров

После запуска напиши боту (как администратор):

```
/add_engineer 987654321 Иван_Петров Проект_А 5000 AED
```

Параметры: `telegram_id имя_без_пробелов проект_без_пробелов депозит валюта`

Инженер должен написать `/start` боту чтобы активировать.

---

## Команды бота

### Для инженеров:
| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и текущий баланс |
| `/balance` | Баланс и статистика расходов |
| `/history` | Последние 5 расходов |
| `/manual 150.50 Carrefour` | Добавить расход вручную |
| 📸 Фото | Отправить фото чека |

### Для администратора:
| Команда | Описание |
|---------|----------|
| `/overview` | Балансы всех инженеров |
| `/report` | Последние 10 транзакций |
| `/add_engineer id имя проект сумма` | Добавить инженера |
| `/topup id сумма` | Пополнить депозит инженера |

---

## Структура Google Sheets

### Лист "Engineers"
| telegram_id | name | project | initial_deposit | balance | currency | added_date | notes |

### Лист "Transactions"
| id | timestamp | date | engineer_id | engineer_name | vendor | amount | currency | category | category_ru | description | balance_after |

---

## Деплой на сервер (опционально)

Чтобы бот работал 24/7, запусти на сервере через systemd или просто nohup:

```bash
nohup python bot.py &
```

Или через Docker:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "bot.py"]
```

---

## Помощь

Если что-то не работает:
1. Проверь что `credentials.json` лежит в папке с ботом
2. Проверь что Service Account email добавлен в таблицу
3. Проверь SPREADSHEET_ID из URL таблицы
