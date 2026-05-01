"""Transaction Log – add and view transactions."""
import streamlit as st
import pandas as pd
from datetime import date

import db, calc, utils

utils.page_config("Transactions")
db.init_db()
utils.inject_css()

st.title("📝 Transactions")

cards = db.get_cards(active_only=True)
if not cards:
    st.info("No cards yet. Add a card first.")
    st.stop()

TRANSACTION_TYPES = ["Purchase", "Fee", "Insurance", "Cash Advance", "Refund"]

# ── Add Transaction form ───────────────────────────────────────────────────────
with st.expander("➕ Add Transaction", expanded=False):
    with st.form("txn_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            card_options = {c["card_id"]: f"{c['card_name']} ({c['card_id']})" for c in cards}
            card_id = st.selectbox("Card", list(card_options.keys()),
                format_func=lambda k: card_options[k])
            txn_date = st.date_input("Date", value=date.today())
            merchant = st.text_input("Merchant / Description")
        with c2:
            txn_type = st.selectbox("Transaction Type", TRANSACTION_TYPES)
            amount = st.number_input("Amount (৳)", min_value=0.01, step=10.0)
            category = st.text_input("Category", help="Auto-filled if merchant is in Categories")
        with c3:
            notes = st.text_area("Notes", height=80)
            installment_id = st.text_input(
                "Installment ID (optional)",
                help="Link to an installment plan e.g. INST001",
            )

        # Auto-fill category from merchant
        if merchant:
            row = db.get_category_for_merchant(merchant)
            if row and not category:
                category = row["category"]
                txn_type = row["transaction_type"]

        submitted = st.form_submit_button("Add Transaction")
        if submitted:
            if not merchant:
                st.error("Merchant is required.")
            else:
                card = db.get_card(card_id)
                points = calc.calc_points(amount, card["points_divisor"])
                txn_id = db.next_id("TXN", "transactions", "transaction_id")
                db.upsert_transaction({
                    "transaction_id": txn_id,
                    "date": str(txn_date),
                    "card_id": card_id,
                    "merchant": merchant.strip(),
                    "installment_id": installment_id.strip(),
                    "transaction_type": txn_type,
                    "category": category.strip(),
                    "amount": round(amount, 2),
                    "notes": notes.strip(),
                })
                st.success(
                    f"Saved {txn_id}: {utils.fmt_bdt(amount)} at {merchant} "
                    f"({points} pts)"
                )
                st.rerun()

# ── Filters ────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">TRANSACTION LOG</div>', unsafe_allow_html=True)

f1, f2, f3, f4 = st.columns(4)
with f1:
    all_cards = [c["card_id"] for c in db.get_cards()]
    filter_card = st.selectbox("Filter by Card", ["All"] + all_cards,
        format_func=lambda k: "All Cards" if k == "All" else
        f"{db.get_card(k)['card_name']} ({k})")
with f2:
    filter_type = st.selectbox("Filter by Type", ["All"] + TRANSACTION_TYPES)
with f3:
    filter_from = st.date_input("From", value=None)
with f4:
    filter_to = st.date_input("To", value=None)

txns = db.get_transactions(
    card_id=None if filter_card == "All" else filter_card,
    from_date=str(filter_from) if filter_from else None,
    to_date=str(filter_to) if filter_to else None,
    txn_type=None if filter_type == "All" else filter_type,
)

# ── Summary stats ──────────────────────────────────────────────────────────────
if txns:
    total_spend = sum(
        r["amount"] for r in txns
        if r["transaction_type"] in db.ADDS_TO_BALANCE
    )
    total_refund = sum(
        r["amount"] for r in txns
        if r["transaction_type"] in db.REDUCES_BALANCE
    )
    card_obj_map = {c["card_id"]: dict(c) for c in db.get_cards()}

    s1, s2, s3 = st.columns(3)
    s1.metric("Transactions shown", len(txns))
    s2.metric("Total Debits", utils.fmt_bdt(total_spend))
    s3.metric("Total Refunds", utils.fmt_bdt(total_refund))

    # Build display dataframe
    rows = []
    for r in txns:
        card_obj = card_obj_map.get(r["card_id"], {})
        card_name = card_obj.get("card_name", r["card_id"]) if card_obj else r["card_id"]
        pts_div = card_obj.get("points_divisor", 100) if card_obj else 100
        pts = calc.calc_points(r["amount"], pts_div) if r["transaction_type"] in db.ADDS_TO_BALANCE else 0
        rows.append({
            "ID": r["transaction_id"],
            "Date": r["date"],
            "Card": card_name,
            "Merchant": r["merchant"],
            "Type": r["transaction_type"],
            "Category": r["category"],
            "Amount": utils.fmt_bdt(r["amount"]),
            "Points": pts if pts else "",
            "Inst.": r["installment_id"] or "",
            "Notes": r["notes"] or "",
        })

    df = pd.DataFrame(rows)

    def _type_color(val):
        if val in db.ADDS_TO_BALANCE:
            return "color: #f87171"
        if val in db.REDUCES_BALANCE:
            return "color: #4ade80"
        return ""

    st.dataframe(
        df.style.map(_type_color, subset=["Type"]),
        use_container_width=True, hide_index=True,
        height=500,
    )

    # ── Delete ────────────────────────────────────────────────────────────────
    with st.expander("Delete a transaction"):
        del_id = st.text_input("Transaction ID to delete (e.g. TXN0042)")
        if st.button("Delete") and del_id:
            db.delete_transaction(del_id.strip().upper())
            st.success(f"Deleted {del_id}.")
            st.rerun()
else:
    st.info("No transactions match the current filters.")
