"""Credit Card Manager – home page."""
import streamlit as st
import db
import calc
import utils
from datetime import date

utils.page_config("Credit Card Manager")
db.init_db()
utils.inject_css()

st.title("💳 Credit Card Manager")
st.caption("A personal credit card tracker — balances, utilization, waiver progress, EMI and more.")

cards = db.get_cards(active_only=True)

# ── Empty state: onboarding ───────────────────────────────────────────────────
if not cards:
    st.markdown("---")
    st.markdown("### Welcome! Let's get started.")
    st.markdown(
        "This is your **private session** — no one else can see your data. "
        "Your information is stored only for this browser session."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            **Step 1 — Add your cards**
            Go to **Cards** in the sidebar and add each of your credit cards:
            bank name, credit limit, statement date, waiver settings, etc.
            """
        )
    with col2:
        st.markdown(
            """
            **Step 2 — Log transactions & payments**
            Use **Transactions** and **Payments** to record activity.
            The Dashboard will update automatically.
            """
        )

    st.markdown("---")
    st.page_link("pages/2_Cards.py", label="➕ Add your first card", icon="💳")
    st.stop()


# ── Loaded state: quick overview ──────────────────────────────────────────────
metrics = calc.get_all_card_metrics()
summary = calc.get_dashboard_summary(metrics)
today   = date.today()

# Key metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Outstanding",  utils.fmt_bdt(summary["total_outstanding"]))
c2.metric("Available Credit",   utils.fmt_bdt(summary["total_available"]))
c3.metric("Total Cards",        len(cards))
c4.metric("Reward Points",      f"{summary['total_points']:,}")

st.divider()

# Alerts
for a in [m for m in metrics if m["payment_status"] in ("Urgent", "Overdue", "Due Soon")]:
    st.error(
        f"⚠️ **{a['card_name']}** — {a['next_action']}  "
        f"(due in {a['days_to_due']} days)"
    )
for a in [m for m in metrics if m["payment_status"] == "Upcoming"]:
    st.warning(
        f"⏰ **{a['card_name']}** — {a['next_action']}  "
        f"(due in {a['days_to_due']} days)"
    )

# Best card banner
best = summary["best_card_to_use"]
bm = next((m for m in metrics if m["card_name"] == best), None)
if bm:
    st.markdown(
        f"""<div class="best-card-banner">
        <div class="icon">⭐</div>
        <div>
            <div class="title">Best Card to Use Right Now</div>
            <div class="name">{bm['card_name']}
            <span style="color:#9ca3af;font-size:.85rem;font-weight:400;">
            — {utils.fmt_pct(bm['live_utilization'])} utilization · {bm['bank']}</span>
            </div>
        </div></div>""",
        unsafe_allow_html=True,
    )

# Navigate
st.markdown("### Navigate")
col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/1_Dashboard.py",    label="📊 Full Dashboard",  icon="📊")
    st.page_link("pages/2_Cards.py",        label="💳 Manage Cards",    icon="💳")
with col2:
    st.page_link("pages/3_Transactions.py", label="📝 Transactions",    icon="📝")
    st.page_link("pages/4_Payments.py",     label="💰 Payments",        icon="💰")
with col3:
    st.page_link("pages/5_Installments.py", label="🔄 Installments",    icon="🔄")
    st.page_link("pages/6_Rewards.py",      label="⭐ Rewards",          icon="⭐")

st.divider()
st.caption(f"Data as of {today.strftime('%d %b %Y')}")
