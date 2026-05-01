"""SQLite database layer for Credit Card Manager."""
import os
import sqlite3
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "credit_cards.db"

ADDS_TO_BALANCE = {"Purchase", "Fee", "Insurance", "Cash Advance"}
REDUCES_BALANCE = {"Refund"}


def _in_streamlit() -> bool:
    """True only when running inside an actual Streamlit script execution."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def _session_db_path() -> str:
    """
    - If the local DB file already exists (personal/local mode) → use it directly.
    - Inside Streamlit without a local DB (cloud/public mode) → each session gets
      its own isolated temp DB so visitors never share or see each other's data.
    - Outside Streamlit (import_excel.py etc.) → use the default file path.
    """
    # Local personal mode: DB file present → always use it
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        return str(DB_PATH)

    # Cloud / fresh install
    if _in_streamlit():
        import streamlit as st
        if "db_path" not in st.session_state:
            fd, tmp = tempfile.mkstemp(suffix=".db", prefix="cc_mgr_")
            os.close(fd)
            st.session_state["db_path"] = tmp
        return st.session_state["db_path"]

    # Scripts running outside Streamlit (import_excel.py, etc.)
    DB_PATH.parent.mkdir(exist_ok=True)
    return str(DB_PATH)


def get_conn():
    path = _session_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cards (
                card_id             TEXT PRIMARY KEY,
                bank                TEXT NOT NULL,
                card_name           TEXT NOT NULL,
                card_number         TEXT DEFAULT '',
                credit_limit        REAL NOT NULL,
                issue_month         INTEGER DEFAULT 1,
                starting_balance    REAL DEFAULT 0,
                balance_sync_amount REAL DEFAULT 0,
                balance_sync_date   TEXT DEFAULT '',
                statement_day       INTEGER DEFAULT 1,
                due_days            INTEGER DEFAULT 15,
                min_due_percent     REAL DEFAULT 5.0,
                min_due_fixed       REAL DEFAULT 500,
                points_divisor      REAL DEFAULT 100,
                utilization_target  REAL DEFAULT 0.30,
                waiver_type         TEXT DEFAULT 'None',
                waiver_target       REAL DEFAULT 0,
                active              INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id      TEXT PRIMARY KEY,
                date                TEXT NOT NULL,
                card_id             TEXT NOT NULL,
                merchant            TEXT DEFAULT '',
                installment_id      TEXT DEFAULT '',
                transaction_type    TEXT DEFAULT 'Purchase',
                category            TEXT DEFAULT '',
                amount              REAL NOT NULL,
                notes               TEXT DEFAULT '',
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                payment_id          TEXT PRIMARY KEY,
                date                TEXT NOT NULL,
                card_id             TEXT NOT NULL,
                payment_method      TEXT DEFAULT '',
                amount              REAL NOT NULL,
                notes               TEXT DEFAULT '',
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            );

            CREATE TABLE IF NOT EXISTS installments (
                installment_id      TEXT PRIMARY KEY,
                card_id             TEXT NOT NULL,
                merchant            TEXT DEFAULT '',
                start_date          TEXT NOT NULL,
                purchase_amount     REAL NOT NULL,
                total_months        INTEGER NOT NULL,
                installment_amount  REAL NOT NULL,
                months_paid         INTEGER DEFAULT 0,
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            );

            CREATE TABLE IF NOT EXISTS rewards (
                reward_id           TEXT PRIMARY KEY,
                date                TEXT NOT NULL,
                card_id             TEXT NOT NULL,
                points_redeemed     INTEGER DEFAULT 0,
                adjustment          INTEGER DEFAULT 0,
                notes               TEXT DEFAULT '',
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            );

            CREATE TABLE IF NOT EXISTS categories (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword             TEXT NOT NULL UNIQUE,
                transaction_type    TEXT DEFAULT 'Purchase',
                category            TEXT DEFAULT '',
                category_type       TEXT DEFAULT 'Spending'
            );
        """)
        # Migrate existing DB: add new columns if they don't exist
        for col, defn in [
            ("balance_sync_amount", "REAL DEFAULT 0"),
            ("balance_sync_date",   "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE cards ADD COLUMN {col} {defn}")
            except Exception:
                pass  # Column already exists


# ── Cards ──────────────────────────────────────────────────────────────────────

def get_cards(active_only=False):
    with get_conn() as conn:
        if active_only:
            return conn.execute(
                "SELECT * FROM cards WHERE active=1 ORDER BY card_id"
            ).fetchall()
        return conn.execute("SELECT * FROM cards ORDER BY card_id").fetchall()


def get_card(card_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM cards WHERE card_id=?", (card_id,)
        ).fetchone()


def upsert_card(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "card_id"
    )
    sql = (
        f"INSERT INTO cards ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(card_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_card(card_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM cards WHERE card_id=?", (card_id,))


# ── Transactions ───────────────────────────────────────────────────────────────

def get_transactions(card_id=None, from_date=None, to_date=None,
                     txn_type=None, category=None, limit=None):
    sql = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    if txn_type:
        sql += " AND transaction_type=?"; params.append(txn_type)
    if category:
        sql += " AND category=?"; params.append(category)
    sql += " ORDER BY date DESC, transaction_id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_transaction_sum(card_id=None, from_date=None, to_date=None, types=None):
    """Sum of ABS(amount) for the given transaction types."""
    if not types:
        return 0.0
    ph = ",".join(["?"] * len(types))
    sql = f"SELECT COALESCE(SUM(ABS(amount)),0) FROM transactions WHERE transaction_type IN ({ph})"
    params = list(types)
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()[0] or 0.0


def count_transactions(card_id=None, from_date=None, to_date=None):
    sql = "SELECT COUNT(*) FROM transactions WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()[0] or 0


def get_spending_by_category(from_date=None, to_date=None, card_id=None):
    sql = """
        SELECT category, COALESCE(SUM(ABS(amount)),0) as total
        FROM transactions
        WHERE transaction_type IN ('Purchase','Fee','Insurance','Cash Advance')
    """
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    sql += " GROUP BY category ORDER BY total DESC"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_monthly_spending(card_id=None):
    sql = """
        SELECT SUBSTR(date,1,7) as month,
               card_id,
               COALESCE(SUM(ABS(amount)),0) as total
        FROM transactions
        WHERE transaction_type IN ('Purchase','Fee','Insurance','Cash Advance')
    """
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    sql += " GROUP BY month, card_id ORDER BY month"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def upsert_transaction(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "transaction_id"
    )
    sql = (
        f"INSERT INTO transactions ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(transaction_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_transaction(txn_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE transaction_id=?", (txn_id,))


# ── Payments ───────────────────────────────────────────────────────────────────

def get_payments(card_id=None, from_date=None, to_date=None):
    sql = "SELECT * FROM payments WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    sql += " ORDER BY date DESC"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_payment_sum(card_id=None, from_date=None, to_date=None):
    sql = "SELECT COALESCE(SUM(amount),0) FROM payments WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if from_date:
        sql += " AND date>=?"; params.append(str(from_date))
    if to_date:
        sql += " AND date<=?"; params.append(str(to_date))
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()[0] or 0.0


def upsert_payment(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "payment_id"
    )
    sql = (
        f"INSERT INTO payments ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(payment_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_payment(pay_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM payments WHERE payment_id=?", (pay_id,))


# ── Installments ───────────────────────────────────────────────────────────────

def get_installments(card_id=None, active_only=False):
    sql = "SELECT * FROM installments WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    if active_only:
        sql += " AND months_paid < total_months"
    sql += " ORDER BY start_date"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def upsert_installment(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "installment_id"
    )
    sql = (
        f"INSERT INTO installments ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(installment_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_installment(inst_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM installments WHERE installment_id=?", (inst_id,)
        )


# ── Rewards ────────────────────────────────────────────────────────────────────

def get_rewards(card_id=None):
    sql = "SELECT * FROM rewards WHERE 1=1"
    params = []
    if card_id:
        sql += " AND card_id=?"; params.append(card_id)
    sql += " ORDER BY date DESC"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_redeemed_points(card_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(points_redeemed - adjustment),0) "
            "FROM rewards WHERE card_id=?",
            (card_id,),
        ).fetchone()
        return int(row[0] or 0)


def upsert_reward(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "reward_id"
    )
    sql = (
        f"INSERT INTO rewards ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(reward_id) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_reward(reward_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM rewards WHERE reward_id=?", (reward_id,))


# ── Categories ─────────────────────────────────────────────────────────────────

def get_categories():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM categories ORDER BY keyword"
        ).fetchall()


def get_category_for_merchant(merchant: str):
    if not merchant:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM categories WHERE UPPER(keyword)=UPPER(?)",
            (merchant,),
        ).fetchone()
        if row:
            return row
        row = conn.execute(
            "SELECT * FROM categories "
            "WHERE UPPER(?) LIKE '%' || UPPER(keyword) || '%' "
            "ORDER BY LENGTH(keyword) DESC LIMIT 1",
            (merchant,),
        ).fetchone()
        return row


def upsert_category(data: dict):
    cols = list(data.keys())
    ph = ",".join(["?"] * len(cols))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in cols if c != "keyword"
    )
    sql = (
        f"INSERT INTO categories ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT(keyword) DO UPDATE SET {updates}"
    )
    with get_conn() as conn:
        conn.execute(sql, list(data.values()))


def delete_category(kw):
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE keyword=?", (kw,))


# ── ID helpers ─────────────────────────────────────────────────────────────────

def next_id(prefix: str, table: str, id_col: str) -> str:
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {id_col} FROM {table} ORDER BY {id_col} DESC LIMIT 1"
        ).fetchone()
    if not row:
        return f"{prefix}0001"
    last = row[0]
    try:
        num = int(last.replace(prefix, "")) + 1
    except (ValueError, AttributeError):
        num = 1
    return f"{prefix}{num:04d}"
