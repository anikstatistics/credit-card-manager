"""Payments – log and view credit card payments."""
import streamlit as st
import pandas as pd
from datetime import date

import db, calc, utils

utils.page_config("Payments")
db.init_db()
utils.inject_css()

st.title("💰 Payments")

cards = db.get_cards(active_only=True)
if not cards:
    st.info("No cards yet. Add a card first.")
    st.stop()

PAYMENT_METHODS = [
    "bKash", "Bank Transfer", "Visa Direct", "Cash",
    "Credit Cash Deposit", "Citybank", "Nagad", "Rocket", "Other",
]

# ── Quick summary of what's due ────────────────────────────────────────────────
st.markdown('<div class="section-header">AMOUNTS DUE</div>', unsafe_allow_html=True)
metrics = calc.get_all_card_metrics()
due_cards = [m for m in metrics if m["statement_balance_remaining"] > 0]
if due_cards:
    c_cols = st.columns(len(due_cards))
    for i, m in enumerate(due_cards):
        color = "#f87171" if m["days_to_due"] <= 3 else (
            "#fbbf24" if m["days_to_due"] <= 7 else "#4f8ef7"
        )
        c_cols[i].markdown(
            f"""<div style="background:#1a1d27;border-radius:10px;border-left:4px solid {color};
            padding:12px 16px;margin-bottom:8px;">
            <div style="font-size:.8rem;color:#9ca3af;">{m['card_name']}</div>
            <div style="font-size:1.1rem;font-weight:700;color:{color};">
            {utils.fmt_bdt(m['statement_balance_remaining'])}</div>
            <div style="font-size:.75rem;color:#9ca3af;">
            Min: {utils.fmt_bdt(m['minimum_due_remaining'])} · Due in {m['days_to_due']}d</div>
            </div>""",
            unsafe_allow_html=True,
        )
else:
    st.success("✅ All statements are cleared — no payments due right now.")

# ── Add Payment form ───────────────────────────────────────────────────────────
with st.expander("➕ Record a Payment", expanded=False):
    with st.form("pay_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            card_opts = {c["card_id"]: f"{c['card_name']} ({c['card_id']})" for c in cards}
            card_id = st.selectbox("Card", list(card_opts.keys()),
                format_func=lambda k: card_opts[k])
            pay_date = st.date_input("Payment Date", value=date.today())
        with c2:
            m_sel = next((m for m in metrics if m["card_id"] == card_id), None)
            suggested = m_sel["statement_balance_remaining"] if m_sel else 0.0
            amount = st.number_input(
                "Amount (৳)",
                min_value=0.01,
                value=round(suggested, 2) if suggested > 0 else 0.01,
                step=100.0,
                help=f"Suggested: {utils.fmt_bdt(suggested)}" if suggested > 0 else "",
            )
            method = st.selectbox("Payment Method", PAYMENT_METHODS)
        with c3:
            notes = st.text_area("Notes", height=80)

        submitted = st.form_submit_button("Record Payment")
        if submitted:
            pay_id = db.next_id("PAY", "payments", "payment_id")
            db.upsert_payment({
                "payment_id": pay_id,
                "date": str(pay_date),
                "card_id": card_id,
                "payment_method": method,
                "amount": round(amount, 2),
                "notes": notes.strip(),
            })
            st.success(f"Saved {pay_id}: {utils.fmt_bdt(amount)} for {card_opts[card_id]}")
            st.rerun()

# ── Payment history ────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">PAYMENT HISTORY</div>', unsafe_allow_html=True)

f1, f2 = st.columns(2)
with f1:
    all_ids = [c["card_id"] for c in db.get_cards()]
    filter_card = st.selectbox("Filter by Card", ["All"] + all_ids,
        format_func=lambda k: "All Cards" if k == "All" else
        f"{db.get_card(k)['card_name']} ({k})")
with f2:
    filter_from = st.date_input("From date", value=None, key="pay_from")

payments = db.get_payments(
    card_id=None if filter_card == "All" else filter_card,
    from_date=str(filter_from) if filter_from else None,
)

if payments:
    card_map = {c["card_id"]: c["card_name"] for c in db.get_cards()}
    total_paid = sum(p["amount"] for p in payments)
    st.metric("Total Payments Shown", utils.fmt_bdt(total_paid))

    rows = [{
        "ID": p["payment_id"],
        "Date": p["date"],
        "Card": card_map.get(p["card_id"], p["card_id"]),
        "Method": p["payment_method"],
        "Amount": utils.fmt_bdt(p["amount"]),
        "Notes": p["notes"] or "",
    } for p in payments]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Delete a payment"):
        del_id = st.text_input("Payment ID to delete (e.g. PAY0005)")
        if st.button("Delete") and del_id:
            db.delete_payment(del_id.strip().upper())
            st.success(f"Deleted {del_id}.")
            st.rerun()
else:
    st.info("No payments found for the selected filters.")
