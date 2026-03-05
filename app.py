"""
Flask backend for FURNI Expense Dashboard
Reads live data from Google Sheets and serves the dashboard
Deploy this on Railway — bot runs locally
"""

import os
import json
from flask import Flask, jsonify, render_template_string, request, Response
from functools import wraps
from sheets_manager import SheetsManager
from config import Config

app = Flask(__name__)
sheets = SheetsManager()

# ── Basic auth for dashboard access ──────────────────────────────────────────

def check_auth(username, password):
    return username == Config.DASHBOARD_USER and password == Config.DASHBOARD_PASS

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip auth if no password set
        if not Config.DASHBOARD_PASS:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Нужна авторизация", 401,
                {"WWW-Authenticate": 'Basic realm="FURNI Dashboard"'}
            )
        return f(*args, **kwargs)
    return decorated

# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/engineers")
@require_auth
def api_engineers():
    """Return all engineers with balances."""
    engineers = sheets.get_all_engineers()
    result = []
    for eng in engineers:
        initial = float(eng.get("initial_deposit", 0))
        balance = float(eng.get("balance", 0))
        spent = initial - balance
        pct = (balance / initial * 100) if initial > 0 else 0

        if pct > 40:
            status = "ok"
        elif pct > 15:
            status = "warn"
        else:
            status = "crit"

        result.append({
            "id": str(eng.get("telegram_id", "")),
            "name": eng.get("name", ""),
            "project": eng.get("project", ""),
            "initial": initial,
            "balance": balance,
            "spent": round(spent, 2),
            "pct": round(pct, 1),
            "currency": eng.get("currency", "AED"),
            "status": status,
        })
    return jsonify(result)


@app.route("/api/transactions")
@require_auth
def api_transactions():
    """Return recent transactions (last 50)."""
    engineer_id = request.args.get("engineer_id")
    txns = sheets.get_transactions(engineer_id=engineer_id, limit=50)
    return jsonify(txns)


@app.route("/api/summary")
@require_auth
def api_summary():
    """Return summary stats for top cards."""
    engineers = sheets.get_all_engineers()
    transactions = sheets.get_transactions(limit=500)

    total_initial = sum(float(e.get("initial_deposit", 0)) for e in engineers)
    total_balance = sum(float(e.get("balance", 0)) for e in engineers)
    total_spent = total_initial - total_balance

    # This month's transactions
    from datetime import datetime
    this_month = datetime.now().strftime("%Y-%m")
    month_txns = [t for t in transactions if str(t.get("date", "")).startswith(this_month)]
    month_spent = sum(float(str(t.get("amount", 0)).replace(",", ".")) for t in month_txns)

    # Category breakdown
    cats = {"transport": 0, "purchase": 0, "components": 0, "other": 0}
    for t in month_txns:
        cat = t.get("category", "other")
        if cat not in cats:
            cat = "other"
        cats[cat] += float(str(t.get("amount", 0)).replace(",", "."))

    # Daily spending last 30 days
    from datetime import timedelta
    today = datetime.now().date()
    daily = {}
    for i in range(30):
        day = (today - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        daily[day] = 0
    for t in transactions:
        d = str(t.get("date", ""))[:10]
        if d in daily:
            daily[d] += float(str(t.get("amount", 0)).replace(",", "."))

    # Alerts: engineers with low balance
    alerts = []
    for e in engineers:
        initial = float(e.get("initial_deposit", 0))
        balance = float(e.get("balance", 0))
        pct = (balance / initial * 100) if initial > 0 else 0
        currency = e.get("currency", "AED")
        if pct <= 10:
            alerts.append({
                "level": "crit",
                "name": e.get("name"),
                "msg": f"Остаток {balance:,.0f} {currency} / {initial:,.0f} {currency} ({pct:.0f}%)"
            })
        elif pct <= 25:
            alerts.append({
                "level": "warn",
                "name": e.get("name"),
                "msg": f"Остаток {balance:,.0f} {currency} / {initial:,.0f} {currency} ({pct:.0f}%)"
            })

    return jsonify({
        "total_initial": round(total_initial, 2),
        "total_balance": round(total_balance, 2),
        "total_spent": round(total_spent, 2),
        "month_spent": round(month_spent, 2),
        "txn_count": len(transactions),
        "engineer_count": len(engineers),
        "categories": cats,
        "daily": [{"date": k, "amount": round(v, 2)} for k, v in daily.items()],
        "alerts": alerts,
    })


@app.route("/api/topup", methods=["POST"])
@require_auth
def api_topup():
    """Top up engineer balance from dashboard."""
    data = request.json
    telegram_id = str(data.get("telegram_id", ""))
    amount = float(data.get("amount", 0))

    if not telegram_id or amount <= 0:
        return jsonify({"ok": False, "error": "Неверные данные"}), 400

    new_balance = sheets.top_up_balance(telegram_id, amount)
    if new_balance is None:
        return jsonify({"ok": False, "error": "Инженер не найден"}), 404

    return jsonify({"ok": True, "new_balance": new_balance})


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@app.route("/")
@require_auth
def dashboard():
    """Serve the dashboard HTML."""
    with open("dashboard.html", "r") as f:
        html = f.read()
    return html


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
