"""Card Management – add, edit, view cards."""
import streamlit as st
import db, calc, utils

utils.page_config("Cards")
db.init_db()
utils.inject_css()

st.title("💳 Cards")

WAIVER_TYPES = ["None", "Transactions", "Spending", "Points"]

# ── Add / Edit form ────────────────────────────────────────────────────────────
with st.expander("➕ Add / Edit Card", expanded=False):
    cards = db.get_cards()
    card_ids = [c["card_id"] for c in cards]

    mode = st.radio("Mode", ["New Card", "Edit Existing"], horizontal=True)
    edit_card = None

    if mode == "Edit Existing" and card_ids:
        sel = st.selectbox("Select card to edit", card_ids)
        edit_card = dict(db.get_card(sel))

    with st.form("card_form"):
        defaults = edit_card or {}

        col1, col2 = st.columns(2)
        with col1:
            card_id = st.text_input("Card ID (e.g. CC1)",
                value=defaults.get("card_id", ""), disabled=(mode == "Edit Existing"))
            bank = st.text_input("Bank Name", value=defaults.get("bank", ""))
            card_name = st.text_input("Card Name", value=defaults.get("card_name", ""))
            card_number = st.text_input(
                "Card Number (masked)", value=defaults.get("card_number", ""),
                help="e.g. 447780******0330",
            )
            credit_limit = st.number_input(
                "Credit Limit (৳)", min_value=0.0,
                value=float(defaults.get("credit_limit", 0)),
                step=1000.0,
            )
            starting_balance = st.number_input(
                "Starting Balance (৳)",
                value=float(defaults.get("starting_balance", 0)),
                step=100.0,
                help="Outstanding balance when this card was first added.",
            )

        with col2:
            issue_month = st.selectbox(
                "Issue Month (for waiver cycle)",
                list(range(1, 13)),
                index=int(defaults.get("issue_month", 1)) - 1,
                format_func=lambda m: [
                    "Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"
                ][m-1],
            )
            statement_day = st.number_input(
                "Statement Day of Month", min_value=1, max_value=31,
                value=int(defaults.get("statement_day", 1)),
            )
            due_days = st.number_input(
                "Days after statement until due", min_value=1, max_value=60,
                value=int(defaults.get("due_days", 15)),
            )
            min_due_percent = st.number_input(
                "Minimum Due %", min_value=0.0, max_value=100.0,
                value=float(defaults.get("min_due_percent", 5.0)),
                step=0.5,
            )
            min_due_fixed = st.number_input(
                "Minimum Due Fixed (৳)", min_value=0.0,
                value=float(defaults.get("min_due_fixed", 500)),
                step=50.0,
                help="Min due = max(fixed, limit%×balance)",
            )
            points_divisor = st.number_input(
                "Points Divisor (৳ per point)",
                min_value=1.0,
                value=float(defaults.get("points_divisor", 100)),
                step=1.0,
                help="1 point per ৳{points_divisor} spent",
            )
            utilization_target = st.slider(
                "Utilization Target %",
                min_value=10, max_value=90,
                value=int(float(defaults.get("utilization_target", 0.30)) * 100),
            ) / 100.0

        st.markdown("**Annual Fee Waiver**")
        wc1, wc2 = st.columns(2)
        with wc1:
            waiver_type = st.selectbox(
                "Waiver Type",
                WAIVER_TYPES,
                index=WAIVER_TYPES.index(defaults.get("waiver_type", "None")),
            )
        with wc2:
            waiver_target = st.number_input(
                "Waiver Target (transactions / ৳ amount / points)",
                min_value=0.0,
                value=float(defaults.get("waiver_target", 0)),
                step=1.0,
            )

        active = st.checkbox("Active", value=bool(defaults.get("active", 1)))

        submitted = st.form_submit_button("Save Card")
        if submitted:
            if not card_id or not bank or not card_name:
                st.error("Card ID, Bank, and Card Name are required.")
            else:
                if mode == "Edit Existing" and edit_card:
                    card_id = edit_card["card_id"]
                db.upsert_card({
                    "card_id": card_id.strip().upper(),
                    "bank": bank.strip(),
                    "card_name": card_name.strip(),
                    "card_number": card_number.strip(),
                    "credit_limit": credit_limit,
                    "issue_month": issue_month,
                    "starting_balance": starting_balance,
                    "statement_day": statement_day,
                    "due_days": due_days,
                    "min_due_percent": min_due_percent,
                    "min_due_fixed": min_due_fixed,
                    "points_divisor": points_divisor,
                    "utilization_target": utilization_target,
                    "waiver_type": waiver_type,
                    "waiver_target": waiver_target,
                    "active": 1 if active else 0,
                })
                st.success(f"Card {card_id} saved.")
                st.rerun()


# ── Card tiles ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">ALL CARDS</div>', unsafe_allow_html=True)

cards = db.get_cards()
if not cards:
    st.info("No cards yet. Add one above.")
    st.stop()

metrics = calc.get_all_card_metrics()

for m in metrics:
    card = db.get_card(m["card_id"])
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
        with col1:
            status_icon = "🟢" if m["usage_priority"] == "Safe" else "🟡"
            st.markdown(f"**{status_icon} {m['card_name']}**")
            st.caption(f"{m['bank']}  ·  {card['card_number']}")
        with col2:
            st.metric("Balance / Limit",
                f"{utils.fmt_bdt(m['live_balance'])} / {utils.fmt_bdt(m['credit_limit'])}")
        with col3:
            util_color = "#4ade80" if m["live_utilization"] < 0.3 else (
                "#fbbf24" if m["live_utilization"] < 0.5 else "#f87171"
            )
            st.markdown(
                f"Util: <span style='color:{util_color};font-weight:700;'>"
                f"{utils.fmt_pct(m['live_utilization'])}</span>",
                unsafe_allow_html=True,
            )
            st.caption(f"Points: {m['reward_points']:,}")
        with col4:
            waiver_pct = m["waiver_progress"] * 100
            st.markdown(
                f"Waiver: **{waiver_pct:.0f}%** · {m['waiver_urgency']}"
            )
            st.caption(f"Eff. Score: {m['efficiency_score']:.3f}")
        with col5:
            if st.button("🗑️", key=f"del_{m['card_id']}",
                         help=f"Delete {m['card_name']}"):
                st.session_state[f"confirm_del_{m['card_id']}"] = True

        if st.session_state.get(f"confirm_del_{m['card_id']}"):
            st.warning(
                f"Delete **{m['card_name']}** and ALL its transactions/payments? "
                "This cannot be undone."
            )
            yes, no = st.columns(2)
            if yes.button("Yes, delete", key=f"yes_{m['card_id']}"):
                db.delete_card(m["card_id"])
                del st.session_state[f"confirm_del_{m['card_id']}"]
                st.rerun()
            if no.button("Cancel", key=f"no_{m['card_id']}"):
                del st.session_state[f"confirm_del_{m['card_id']}"]
                st.rerun()

        st.divider()
