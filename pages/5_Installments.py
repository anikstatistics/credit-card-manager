"""Installments – track EMI / installment plans."""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import calendar

import db, utils

utils.page_config("Installments")
db.init_db()
utils.inject_css()

st.title("🔄 Installments")

cards = db.get_cards(active_only=True)
if not cards:
    st.info("No cards yet.")
    st.stop()

def _end_date(start_str: str, total_months: int) -> str:
    try:
        y, m, d = map(int, start_str.split("-"))
        end_m = m + total_months
        end_y = y + (end_m - 1) // 12
        end_m = ((end_m - 1) % 12) + 1
        max_d = calendar.monthrange(end_y, end_m)[1]
        return date(end_y, end_m, min(d, max_d)).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ── Add / Edit form ────────────────────────────────────────────────────────────
with st.expander("➕ Add / Edit Installment Plan", expanded=False):
    inst_list = db.get_installments()
    inst_ids = [i["installment_id"] for i in inst_list]

    mode = st.radio("Mode", ["New Plan", "Edit Existing"], horizontal=True)
    edit_inst = None
    if mode == "Edit Existing" and inst_ids:
        sel = st.selectbox("Select plan", inst_ids)
        edit_inst = dict(db.get_installments())
        edit_inst = dict(next(i for i in inst_list if i["installment_id"] == sel))

    with st.form("inst_form"):
        defaults = edit_inst or {}
        c1, c2 = st.columns(2)
        with c1:
            inst_id = st.text_input(
                "Installment ID (e.g. INST001)",
                value=defaults.get("installment_id", ""),
                disabled=(mode == "Edit Existing"),
            )
            card_opts = {c["card_id"]: f"{c['card_name']} ({c['card_id']})" for c in cards}
            card_id = st.selectbox(
                "Card",
                list(card_opts.keys()),
                format_func=lambda k: card_opts[k],
                index=list(card_opts.keys()).index(defaults["card_id"])
                if defaults.get("card_id") in card_opts else 0,
            )
            merchant = st.text_input("Merchant / Description",
                value=defaults.get("merchant", ""))
            start_date = st.date_input(
                "Start Date",
                value=date.fromisoformat(defaults["start_date"])
                if defaults.get("start_date") else date.today(),
            )

        with c2:
            purchase_amount = st.number_input(
                "Purchase Amount (৳)", min_value=0.01, step=100.0,
                value=float(defaults.get("purchase_amount", 0)) or 0.01,
            )
            total_months = st.number_input(
                "Total Months", min_value=1, max_value=60,
                value=int(defaults.get("total_months", 3)),
            )
            _inst_default = float(defaults.get("installment_amount", 0)) or round(purchase_amount / total_months, 2)
            installment_amount = st.number_input(
                "Monthly Installment (৳)", min_value=0.01, step=10.0,
                value=max(0.01, _inst_default),
            )
            months_paid = st.number_input(
                "Months Already Paid", min_value=0,
                max_value=int(defaults.get("total_months", 60)),
                value=int(defaults.get("months_paid", 0)),
            )

        submitted = st.form_submit_button("Save Plan")
        if submitted:
            if not inst_id:
                inst_id = db.next_id("INST", "installments", "installment_id")
            if mode == "Edit Existing" and edit_inst:
                inst_id = edit_inst["installment_id"]
            db.upsert_installment({
                "installment_id": inst_id.strip().upper(),
                "card_id": card_id,
                "merchant": merchant.strip(),
                "start_date": str(start_date),
                "purchase_amount": round(purchase_amount, 2),
                "total_months": int(total_months),
                "installment_amount": round(installment_amount, 2),
                "months_paid": int(months_paid),
            })
            st.success(f"Saved {inst_id}.")
            st.rerun()


# ── Summary ────────────────────────────────────────────────────────────────────
all_insts = db.get_installments()
active_insts = [i for i in all_insts if i["months_paid"] < i["total_months"]]
card_map = {c["card_id"]: c["card_name"] for c in db.get_cards()}

if active_insts:
    total_emi = sum(i["installment_amount"] for i in active_insts)
    total_remaining = sum(
        i["installment_amount"] * (i["total_months"] - i["months_paid"])
        for i in active_insts
    )
    s1, s2, s3 = st.columns(3)
    s1.metric("Active Plans",      len(active_insts))
    s2.metric("Monthly EMI Total", utils.fmt_bdt(total_emi))
    s3.metric("Total Remaining",   utils.fmt_bdt(total_remaining))

# ── Active plans ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">ACTIVE PLANS</div>', unsafe_allow_html=True)

if not all_insts:
    st.info("No installment plans recorded yet.")
else:
    for i in sorted(all_insts, key=lambda x: (x["months_paid"] >= x["total_months"], x["start_date"])):
        months_left = i["total_months"] - i["months_paid"]
        remaining = i["installment_amount"] * months_left
        progress = i["months_paid"] / i["total_months"] if i["total_months"] else 1.0
        status = "✅ Closed" if months_left <= 0 else f"🔄 Active ({months_left} months left)"
        end = _end_date(i["start_date"], i["total_months"])
        prog_color = "#4ade80" if months_left <= 0 else (
            "#fbbf24" if progress >= 0.5 else "#4f8ef7"
        )

        with st.container():
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown(
                    f"**{i['installment_id']}** · {i['merchant']}"
                )
                st.caption(
                    f"{card_map.get(i['card_id'], i['card_id'])} · "
                    f"Started {i['start_date']} · Ends {end}"
                )
            with c2:
                st.markdown(
                    f"Purchase: **{utils.fmt_bdt(i['purchase_amount'])}**  \n"
                    f"Monthly: {utils.fmt_bdt(i['installment_amount'])}"
                )
            with c3:
                st.markdown(
                    f"{i['months_paid']}/{i['total_months']} months paid  \n"
                    f"Remaining: **{utils.fmt_bdt(remaining)}**"
                )
                st.markdown(
                    utils.progress_bar_html(progress, prog_color),
                    unsafe_allow_html=True,
                )
                st.caption(f"{progress*100:.0f}% complete · {status}")
            with c4:
                if months_left > 0:
                    if st.button("＋1 Month", key=f"pay_{i['installment_id']}",
                                 help="Mark one more month as paid"):
                        db.upsert_installment({
                            **dict(i),
                            "months_paid": i["months_paid"] + 1,
                        })
                        st.rerun()
                if st.button("🗑️", key=f"del_{i['installment_id']}"):
                    db.delete_installment(i["installment_id"])
                    st.rerun()
        st.divider()
