"""Business logic and calculations for Credit Card Manager."""
import calendar
import math
from datetime import date, timedelta

import db


# ── Date helpers ───────────────────────────────────────────────────────────────

def _make_date(year: int, month: int, day: int) -> date:
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, max_day))


def get_statement_dates(statement_day: int, today: date = None):
    """Return (last_statement_date, next_statement_date)."""
    if today is None:
        today = date.today()
    y, m = today.year, today.month
    current = _make_date(y, m, statement_day)
    if current <= today:
        last = current
        nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
        nxt = _make_date(ny, nm, statement_day)
    else:
        nxt = current
        pm, py = (m - 1, y) if m > 1 else (12, y - 1)
        last = _make_date(py, pm, statement_day)
    return last, nxt


def get_waiver_cycle(issue_month: int, today: date = None):
    """Return (cycle_start, cycle_end) for the current annual waiver cycle."""
    if today is None:
        today = date.today()
    y = today.year
    start = date(y, issue_month, 1) if today.month >= issue_month else date(y - 1, issue_month, 1)
    end = date(start.year + 1, issue_month, 1) - timedelta(days=1)
    return start, end


# ── Balance calculations ───────────────────────────────────────────────────────

def get_live_balance(card, today: date = None) -> float:
    """
    Balance = sync_amount + charges_after_sync - payments_after_sync.
    sync_date is the last date already baked into sync_amount (exclusive lower bound).
    """
    if today is None:
        today = date.today()
    cid = card["card_id"]
    sync_amt  = card.get("balance_sync_amount") or 0.0
    sync_date = card.get("balance_sync_date") or ""
    today_str = str(today)
    pos  = db.get_transaction_sum(cid, from_date=sync_date or None,
                                   to_date=today_str, types=list(db.ADDS_TO_BALANCE))
    neg  = db.get_transaction_sum(cid, from_date=sync_date or None,
                                   to_date=today_str, types=list(db.REDUCES_BALANCE))
    paid = db.get_payment_sum(cid, from_date=sync_date or None, to_date=today_str)
    return max(0.0, sync_amt + pos - neg - paid)


def get_statement_balance(card, statement_date: date) -> float:
    """
    Reverse post-statement activity from the sync point to find the balance
    that was on the statement.  Works correctly with imported historical data.
    """
    cid = card["card_id"]
    sync_amt  = card.get("balance_sync_amount") or 0.0
    sync_date = card.get("balance_sync_date") or ""

    from_stmt = str(statement_date + timedelta(days=1))
    # Only look at activity between statement+1 and sync_date
    to_d = sync_date if sync_date else str(date.today())

    post_pos  = db.get_transaction_sum(cid, from_date=from_stmt, to_date=to_d,
                                        types=list(db.ADDS_TO_BALANCE))
    post_neg  = db.get_transaction_sum(cid, from_date=from_stmt, to_date=to_d,
                                        types=list(db.REDUCES_BALANCE))
    post_paid = db.get_payment_sum(cid, from_date=from_stmt, to_date=to_d)

    # statement_balance = live_balance_at_sync  − net_post_statement_charges
    return max(0.0, sync_amt - post_pos + post_neg + post_paid)


# ── Points ─────────────────────────────────────────────────────────────────────

def calc_points(amount: float, points_divisor: float) -> int:
    if points_divisor and points_divisor > 0:
        return math.floor(abs(amount) / points_divisor)
    return 0


def get_total_points_earned(card_id: str, points_divisor: float,
                             from_date=None, to_date=None) -> int:
    rows = db.get_transactions(card_id, from_date=from_date, to_date=to_date)
    total = 0
    for r in rows:
        if r["transaction_type"] in db.ADDS_TO_BALANCE:
            total += calc_points(r["amount"], points_divisor)
    return total


def get_reward_points(card_id: str, points_divisor: float) -> int:
    earned = get_total_points_earned(card_id, points_divisor)
    redeemed = db.get_redeemed_points(card_id)
    return max(0, earned - redeemed)


# ── Waiver ─────────────────────────────────────────────────────────────────────

def calc_waiver(waiver_type: str, waiver_target: float,
                txns: int, spending: float, _points: int = 0):
    """Return (progress_0_to_1, remaining_value)."""
    if not waiver_type or waiver_type in ("None", ""):
        return 1.0, 0
    if waiver_target <= 0:
        return 1.0, 0
    if waiver_type == "Transactions":
        prog = min(1.0, txns / waiver_target)
        rem = max(0, waiver_target - txns)
    elif waiver_type == "Spending":
        prog = min(1.0, spending / waiver_target)
        rem = max(0.0, waiver_target - spending)
    elif waiver_type == "Points":
        # Waiver_Target for "Points" type is a spending threshold in BDT
        prog = min(1.0, spending / waiver_target)
        rem = max(0.0, waiver_target - spending)
    else:
        prog, rem = 1.0, 0
    return prog, rem


def get_waiver_urgency(progress: float, waiver_type: str) -> str:
    if not waiver_type or waiver_type in ("None", ""):
        return "Lifetime Free"
    if progress >= 1.0:
        return "Completed"
    if progress >= 0.8:
        return "Almost There"
    if progress >= 0.5:
        return "On Track"
    return "Low"


# ── Efficiency score ───────────────────────────────────────────────────────────

def calc_efficiency(utilization: float, waiver_progress: float, txn_count: int) -> float:
    util_score = max(0.0, 1.0 - utilization / 0.5)
    waiver_score = waiver_progress
    activity_score = min(1.0, txn_count / 40)
    return round(0.40 * waiver_score + 0.40 * util_score + 0.20 * activity_score, 3)


# ── Average daily spend ────────────────────────────────────────────────────────

def get_avg_daily_spending(card_id: str, today: date = None) -> float:
    if today is None:
        today = date.today()
    from_d = today - timedelta(days=30)
    total = db.get_transaction_sum(
        card_id, from_date=str(from_d), to_date=str(today),
        types=list(db.ADDS_TO_BALANCE),
    )
    return total / 30.0


# ── Status labels ──────────────────────────────────────────────────────────────

def get_statement_status(days_to_stmt: int) -> str:
    if days_to_stmt < 0:
        return "Closing Soon"
    if days_to_stmt == 0:
        return "Statement Today"
    if days_to_stmt <= 5:
        return "Near Statement"
    return "Fresh Cycle"


def get_payment_status(stmt_bal_remaining: float, min_due_remaining: float,
                       days_to_due: int) -> str:
    if stmt_bal_remaining <= 0 and min_due_remaining <= 0:
        return "Done"
    if days_to_due < 0:
        return "Overdue"
    if days_to_due <= 3:
        return "Urgent"
    if days_to_due <= 7:
        return "Due Soon"
    if days_to_due <= 14:
        return "Upcoming"
    return "Safe"


def get_next_action(stmt_bal_remaining: float, min_due_remaining: float,
                    waiver_type: str, waiver_progress: float, waiver_remaining) -> str:
    if stmt_bal_remaining > 0:
        if min_due_remaining > 0 and min_due_remaining < stmt_bal_remaining:
            return f"Pay {fmt(stmt_bal_remaining)} (or at least {fmt(min_due_remaining)})"
        return f"Pay {fmt(stmt_bal_remaining)}"
    if waiver_type and waiver_type not in ("None", "") and waiver_progress < 1.0:
        if waiver_type == "Transactions":
            return f"Make {int(waiver_remaining)} more transactions"
        if waiver_type == "Spending":
            return f"Spend {fmt(waiver_remaining)} more"
        if waiver_type == "Points":
            return f"Earn {int(waiver_remaining)} more points"
    if not waiver_type or waiver_type in ("None", ""):
        return "Use freely"
    return "Waiver secured"


def fmt(amount: float) -> str:
    return f"৳{amount:,.2f}"


# ── Recommendation score ───────────────────────────────────────────────────────

def calc_recommendation_score(live_util: float, waiver_progress: float,
                               waiver_type: str, waiver_remaining,
                               stmt_bal_remaining: float, days_to_due: int) -> float:
    """
    Higher = use this card first.
    Key insight: cards that still need TRANSACTIONS for waiver get the highest
    priority so the user earns the annual fee waiver. Lifetime-free cards get
    the lowest priority (no urgency to use them).
    """
    # Waiver urgency bonus
    if waiver_type == "Transactions" and waiver_progress < 1.0:
        # More remaining transactions → more urgent to use this card
        waiver_bonus = 100 + float(waiver_remaining) * 5
    elif waiver_type in ("Spending", "Points") and waiver_progress < 1.0:
        waiver_bonus = 60
    elif waiver_progress >= 1.0 and waiver_type not in ("None", ""):
        waiver_bonus = 50   # Waiver achieved — safe to use
    else:
        waiver_bonus = 0    # Lifetime free — no urgency

    # Utilization penalty: prefer cards with headroom
    util_penalty = live_util * 150

    # Payment penalty: don't recommend if a large unpaid bill is due soon
    if stmt_bal_remaining > 0 and days_to_due <= 7:
        payment_penalty = 30
    else:
        payment_penalty = 0

    return round(100 + waiver_bonus - util_penalty - payment_penalty, 2)


# ── Master per-card metrics ────────────────────────────────────────────────────

def get_card_metrics(card, today: date = None) -> dict:
    if today is None:
        today = date.today()

    cid = card["card_id"]
    limit = card["credit_limit"]
    stmt_day = card["statement_day"]
    due_days_cfg = card["due_days"]
    min_pct = card["min_due_percent"]
    min_fixed = card["min_due_fixed"]
    points_div = card["points_divisor"]
    issue_mo = card["issue_month"]
    waiver_type = card["waiver_type"]
    waiver_target = card["waiver_target"]
    util_target = card["utilization_target"]

    last_stmt, next_stmt = get_statement_dates(stmt_day, today)
    due_date = last_stmt + timedelta(days=due_days_cfg)
    next_due = next_stmt + timedelta(days=due_days_cfg)

    live_bal = get_live_balance(card, today)
    stmt_bal = get_statement_balance(card, last_stmt)
    available = max(0.0, limit - live_bal)

    min_due = max(min_fixed, stmt_bal * min_pct / 100.0) if stmt_bal > 0 else 0.0

    from_stmt_str = str(last_stmt + timedelta(days=1))
    pay_after_stmt = db.get_payment_sum(cid, from_date=from_stmt_str)

    min_due_remaining = max(0.0, min_due - pay_after_stmt)
    stmt_bal_remaining = max(0.0, stmt_bal - pay_after_stmt)

    reward_points = get_reward_points(cid, points_div)

    stmt_util = stmt_bal / limit if limit > 0 else 0.0
    live_util = live_bal / limit if limit > 0 else 0.0
    live_util = max(0.0, live_util)

    days_to_stmt = (next_stmt - today).days
    if stmt_bal_remaining > 0 and due_date >= today:
        days_to_due = (due_date - today).days
    else:
        days_to_due = (next_due - today).days

    cycle_start, cycle_end = get_waiver_cycle(issue_mo, today)
    cs, ce = str(cycle_start), str(cycle_end)
    txns_in_cycle = db.count_transactions(cid, from_date=cs, to_date=ce)
    spending_in_cycle = db.get_transaction_sum(
        cid, from_date=cs, to_date=ce,
        types=list(db.ADDS_TO_BALANCE),
    )
    points_in_cycle = get_total_points_earned(cid, points_div, from_date=cs, to_date=ce)
    waiver_prog, waiver_rem = calc_waiver(
        waiver_type, waiver_target,
        txns_in_cycle, spending_in_cycle, points_in_cycle,
    )

    insts = db.get_installments(cid, active_only=True)
    monthly_emi = sum(i["installment_amount"] for i in insts)
    months_left = max((i["total_months"] - i["months_paid"] for i in insts), default=0)
    future_emi = sum(
        i["installment_amount"] * (i["total_months"] - i["months_paid"])
        for i in insts
    )

    avg_daily = get_avg_daily_spending(cid, today)
    forecast_bal = live_bal + avg_daily * max(0, days_to_stmt)
    forecast_util = max(0.0, forecast_bal / limit) if limit > 0 else 0.0

    eff_score = calc_efficiency(live_util, waiver_prog, txns_in_cycle)
    stmt_status = get_statement_status(days_to_stmt)
    pay_status = get_payment_status(stmt_bal_remaining, min_due_remaining, days_to_due)
    usage_priority = "Safe" if live_util <= util_target else "Caution"
    next_action = get_next_action(
        stmt_bal_remaining, min_due_remaining,
        waiver_type, waiver_prog, waiver_rem,
    )
    rec_score = calc_recommendation_score(
        live_util, waiver_prog, waiver_type, waiver_rem,
        stmt_bal_remaining, days_to_due,
    )

    total_spending = db.get_transaction_sum(cid, types=list(db.ADDS_TO_BALANCE))
    total_payments = db.get_payment_sum(cid)

    return {
        "card_id": cid,
        "card_name": card["card_name"],
        "bank": card["bank"],
        "credit_limit": limit,
        "live_balance": round(live_bal, 2),
        "statement_balance": round(stmt_bal, 2),
        "available_credit": round(available, 2),
        "minimum_due": round(min_due, 2),
        "payments_after_statement": round(pay_after_stmt, 2),
        "minimum_due_remaining": round(min_due_remaining, 2),
        "statement_balance_remaining": round(stmt_bal_remaining, 2),
        "reward_points": reward_points,
        "statement_utilization": stmt_util,
        "live_utilization": live_util,
        "utilization_target": util_target,
        "last_statement_date": last_stmt,
        "next_statement_date": next_stmt,
        "due_date": due_date,
        "next_due_date": next_due,
        "days_to_statement": days_to_stmt,
        "days_to_due": days_to_due,
        "waiver_type": waiver_type,
        "waiver_target": waiver_target,
        "waiver_progress": waiver_prog,
        "waiver_remaining": waiver_rem,
        "waiver_urgency": get_waiver_urgency(waiver_prog, waiver_type),
        "transactions_in_cycle": txns_in_cycle,
        "spending_in_cycle": round(spending_in_cycle, 2),
        "points_in_cycle": points_in_cycle,
        "monthly_emi": round(monthly_emi, 2),
        "installment_months_left": months_left,
        "future_emi_total": round(future_emi, 2),
        "active_installments": len(insts),
        "forecast_utilization": forecast_util,
        "efficiency_score": eff_score,
        "statement_status": stmt_status,
        "payment_status": pay_status,
        "usage_priority": usage_priority,
        "next_action": next_action,
        "recommendation_score": rec_score,
        "total_spending": round(total_spending, 2),
        "total_payments": round(total_payments, 2),
    }


def get_all_card_metrics(today: date = None) -> list:
    cards = db.get_cards(active_only=True)
    return [get_card_metrics(dict(c), today) for c in cards]


# ── Dashboard-level aggregates ─────────────────────────────────────────────────

def get_dashboard_summary(metrics: list) -> dict:
    total_outstanding = sum(m["live_balance"] for m in metrics)
    total_available = sum(m["available_credit"] for m in metrics)
    total_limit = sum(m["credit_limit"] for m in metrics)
    total_spending = sum(m["total_spending"] for m in metrics)
    total_payments = sum(m["total_payments"] for m in metrics)
    total_points = sum(m["reward_points"] for m in metrics)
    monthly_emi = sum(m["monthly_emi"] for m in metrics)
    total_future_emi = sum(m["future_emi_total"] for m in metrics)

    total_fees = db.get_transaction_sum(types=["Fee", "Insurance"])
    total_interest = db.get_transaction_sum(types=["Cash Advance"])

    longest_inst = max((m["installment_months_left"] for m in metrics), default=0)

    cards_needing_payment = [
        m for m in metrics if m["statement_balance_remaining"] > 0
    ]
    highest_util = max(metrics, key=lambda m: m["live_utilization"], default=None)
    best_card = max(metrics, key=lambda m: m["recommendation_score"], default=None)
    next_due_card = min(
        [m for m in metrics if m["days_to_due"] >= 0],
        key=lambda m: m["days_to_due"],
        default=None,
    )

    monthly_rows = db.get_monthly_spending()
    monthly_totals = {}
    for r in monthly_rows:
        monthly_totals[r["month"]] = monthly_totals.get(r["month"], 0) + r["total"]
    avg_monthly = (
        sum(monthly_totals.values()) / len(monthly_totals) if monthly_totals else 0
    )

    today = date.today()
    current_month = today.strftime("%Y-%m")
    current_month_spending = monthly_totals.get(current_month, 0)

    next_stmt_card = min(
        [m for m in metrics if m["days_to_statement"] >= 0],
        key=lambda m: m["days_to_statement"],
        default=None,
    )

    return {
        "total_outstanding": round(total_outstanding, 2),
        "total_available": round(total_available, 2),
        "total_limit": total_limit,
        "total_spending": round(total_spending, 2),
        "total_payments": round(total_payments, 2),
        "total_points": total_points,
        "monthly_emi": round(monthly_emi, 2),
        "total_future_emi": round(total_future_emi, 2),
        "total_fees": round(total_fees, 2),
        "total_interest": round(total_interest, 2),
        "longest_installment": longest_inst,
        "highest_util_card": highest_util["card_name"] if highest_util else "-",
        "best_card_to_use": best_card["card_name"] if best_card else "-",
        "next_due_card": next_due_card,
        "next_stmt_card": next_stmt_card,
        "avg_monthly_spending": round(avg_monthly, 2),
        "current_month_spending": round(current_month_spending, 2),
        "cards_needing_payment": cards_needing_payment,
    }
