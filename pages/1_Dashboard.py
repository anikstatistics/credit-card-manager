"""Full Dashboard – replicates Excel dashboard output."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

import db, calc, utils

utils.page_config("Dashboard")
db.init_db()
utils.inject_css()

st.title("📊 Dashboard")

cards = db.get_cards(active_only=True)
if not cards:
    st.info("No cards yet. Add cards via the Cards page.")
    st.stop()

today = date.today()
metrics = calc.get_all_card_metrics(today)
summary = calc.get_dashboard_summary(metrics)


# ══════════════════════════════════════════════════════════════════════════════
#  KEY METRICS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">KEY METRICS</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Outstanding",     utils.fmt_bdt(summary["total_outstanding"]))
c2.metric("Total Available Credit",utils.fmt_bdt(summary["total_available"]))
c3.metric("Total Spending (all)",  utils.fmt_bdt(summary["total_spending"]))
c4.metric("Total Payments (all)",  utils.fmt_bdt(summary["total_payments"]))

c5, c6, c7, c8 = st.columns(4)
c5.metric("Total Fees & Charges",  utils.fmt_bdt(summary["total_fees"]))
c6.metric("Monthly EMI Burden",    utils.fmt_bdt(summary["monthly_emi"]))
c7.metric("Total Reward Points",   f"{summary['total_points']:,}")
c8.metric("Avg Monthly Spending",  utils.fmt_bdt(summary["avg_monthly_spending"]))


# ══════════════════════════════════════════════════════════════════════════════
#  NEXT BEST ACTION + BEST CARD
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">RECOMMENDATIONS</div>', unsafe_allow_html=True)

col_a, col_b = st.columns(2)
with col_a:
    best_name = summary["best_card_to_use"]
    bm = next((m for m in metrics if m["card_name"] == best_name), None)
    if bm:
        st.markdown(
            f"""<div class="best-card-banner">
            <div class="icon">⭐</div>
            <div>
                <div class="title">Best Card to Use</div>
                <div class="name">{bm['card_name']}<span style="color:#9ca3af;
                font-size:.85rem;font-weight:400;"> — {utils.fmt_pct(bm['live_utilization'])}
                utilization</span></div>
            </div></div>""",
            unsafe_allow_html=True,
        )

with col_b:
    ndc = summary["next_due_card"]
    if ndc:
        days_label = f"{ndc['days_to_due']} days" if ndc["days_to_due"] > 0 else "Today"
        color = "#f87171" if ndc["days_to_due"] <= 3 else (
            "#fbbf24" if ndc["days_to_due"] <= 7 else "#4f8ef7"
        )
        st.markdown(
            f"""<div class="best-card-banner" style="border-color:{color};">
            <div class="icon">⏰</div>
            <div>
                <div class="title">Next Payment Due</div>
                <div class="name">{ndc['card_name']}<span style="color:{color};
                font-size:.85rem;font-weight:400;"> — {days_label} remaining</span></div>
            </div></div>""",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PER-CARD SUMMARY TILES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">CARD OVERVIEW</div>', unsafe_allow_html=True)

cols = st.columns(3)
for i, m in enumerate(metrics):
    with cols[i % 3]:
        st.markdown(utils.card_tile_html(m), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MONITORS  (tabs)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">MONITORS</div>', unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Utilization", "Payment Watch", "Waiver Tracker",
    "Installments", "Card Efficiency",
])


# ── Utilization Monitor ────────────────────────────────────────────────────────
with tab1:
    rows = []
    for m in sorted(metrics, key=lambda x: -x["live_utilization"]):
        rows.append({
            "Card": m["card_name"],
            "Limit": utils.fmt_bdt(m["credit_limit"]),
            "Balance": utils.fmt_bdt(m["live_balance"]),
            "Utilization": utils.fmt_pct(m["live_utilization"]),
            "Forecast Util": utils.fmt_pct(m["forecast_utilization"]),
            "Days to Stmt": (
                str(m["days_to_statement"]) if m["days_to_statement"] >= 0
                else "Past"
            ),
            "Status": m["usage_priority"],
        })
    df = pd.DataFrame(rows)

    def _color_util(val):
        try:
            v = float(val.strip("%")) / 100
        except Exception:
            return ""
        if v >= 0.5:
            return "color: #f87171"
        if v >= 0.3:
            return "color: #fbbf24"
        return "color: #4ade80"

    st.dataframe(
        df.style.map(_color_util, subset=["Utilization", "Forecast Util"]),
        use_container_width=True, hide_index=True,
    )


# ── Payment Watch ──────────────────────────────────────────────────────────────
with tab2:
    rows = []
    for m in sorted(metrics, key=lambda x: x["days_to_due"]):
        rows.append({
            "Card": m["card_name"],
            "Live Balance": utils.fmt_bdt(m["live_balance"]),
            "Stmt Balance": utils.fmt_bdt(m["statement_balance"]),
            "Min Due": utils.fmt_bdt(m["minimum_due"]),
            "Min Due Remaining": utils.fmt_bdt(m["minimum_due_remaining"]),
            "Stmt Bal Remaining": utils.fmt_bdt(m["statement_balance_remaining"]),
            "Days to Due": (
                str(m["days_to_due"]) if m["days_to_due"] >= 0 else "Overdue"
            ),
            "Status": m["payment_status"],
        })
    df = pd.DataFrame(rows)

    def _color_status(val):
        c = utils.status_color(str(val))
        return f"color: {c}"

    st.dataframe(
        df.style.map(_color_status, subset=["Status"]),
        use_container_width=True, hide_index=True,
    )


# ── Waiver Tracker ─────────────────────────────────────────────────────────────
with tab3:
    rows = []
    for m in metrics:
        wt = m["waiver_type"] or "None"
        tgt = (
            str(int(m["waiver_target"])) if wt == "Transactions"
            else utils.fmt_bdt(m["waiver_target"]) if wt in ("Spending", "Points")
            else "—"
        )
        done = (
            str(m["transactions_in_cycle"]) if wt == "Transactions"
            else utils.fmt_bdt(m["spending_in_cycle"]) if wt == "Spending"
            else str(m["points_in_cycle"]) if wt == "Points"
            else "Lifetime"
        )
        rows.append({
            "Card": m["card_name"],
            "Waiver Type": wt,
            "Target": tgt,
            "Done": done,
            "Progress": f"{m['waiver_progress']*100:.0f}%",
            "Status": m["waiver_urgency"],
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.map(lambda v: f"color:{utils.status_color(v)}", subset=["Status"]),
        use_container_width=True, hide_index=True,
    )


# ── Installment Monitor ────────────────────────────────────────────────────────
with tab4:
    insts = db.get_installments()
    if not insts:
        st.info("No installments recorded.")
    else:
        rows = []
        for i in insts:
            months_left = i["total_months"] - i["months_paid"]
            remaining = i["installment_amount"] * months_left
            status = "Active" if months_left > 0 else "Closed"
            progress = i["months_paid"] / i["total_months"] if i["total_months"] else 1
            card = db.get_card(i["card_id"])
            rows.append({
                "ID": i["installment_id"],
                "Card": card["card_name"] if card else i["card_id"],
                "Merchant": i["merchant"],
                "Purchase": utils.fmt_bdt(i["purchase_amount"]),
                "Monthly": utils.fmt_bdt(i["installment_amount"]),
                "Months": f"{i['months_paid']}/{i['total_months']}",
                "Remaining": utils.fmt_bdt(remaining),
                "Progress": f"{progress*100:.0f}%",
                "Status": status,
            })
        df = pd.DataFrame(rows)
        st.dataframe(
            df.style.map(
                lambda v: "color:#4ade80" if v == "Closed" else "color:#fbbf24",
                subset=["Status"],
            ),
            use_container_width=True, hide_index=True,
        )

        # Summary row
        active_only = [r for r in rows if r["Status"] == "Active"]
        if active_only:
            df_act = pd.DataFrame(active_only)
            st.markdown(
                f"**Active installments:** {len(active_only)} cards · "
                f"Total monthly EMI: **{utils.fmt_bdt(summary['monthly_emi'])}** · "
                f"Total future commitment: **{utils.fmt_bdt(summary['total_future_emi'])}**"
            )


# ── Card Efficiency ────────────────────────────────────────────────────────────
with tab5:
    rows = []
    for m in sorted(metrics, key=lambda x: -x["efficiency_score"]):
        rows.append({
            "Rank": "",
            "Card": m["card_name"],
            "Efficiency Score": f"{m['efficiency_score']:.3f}",
            "Utilization": utils.fmt_pct(m["live_utilization"]),
            "Waiver": f"{m['waiver_progress']*100:.0f}%",
            "Txns (cycle)": m["transactions_in_cycle"],
            "Spending": utils.fmt_bdt(m["total_spending"]),
        })
    for i, r in enumerate(rows):
        r["Rank"] = f"#{i+1}"
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CHARTS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">SPENDING ANALYTICS</div>', unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns(2)

# ── Spending by Category ───────────────────────────────────────────────────────
with chart_col1:
    st.subheader("Spending by Category")
    cat_rows = db.get_spending_by_category()
    if cat_rows:
        df_cat = pd.DataFrame([dict(r) for r in cat_rows])
        df_cat = df_cat[df_cat["total"] > 0].head(12)
        fig = px.bar(
            df_cat, x="total", y="category", orientation="h",
            color="total",
            color_continuous_scale=["#2d5a9e", "#4f8ef7", "#93c5fd"],
            labels={"total": "Amount (৳)", "category": ""},
            text=df_cat["total"].apply(lambda x: f"৳{x:,.0f}"),
        )
        fig.update_layout(
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117",
            font_color="#e0e4f0", coloraxis_showscale=False,
            margin=dict(l=0, r=0, t=0, b=0), height=360,
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No transaction data yet.")

# ── Monthly Spending ───────────────────────────────────────────────────────────
with chart_col2:
    st.subheader("Monthly Spending")
    monthly = db.get_monthly_spending()
    if monthly:
        df_mo = pd.DataFrame([dict(r) for r in monthly])
        monthly_total = df_mo.groupby("month")["total"].sum().reset_index()
        fig = px.bar(
            monthly_total, x="month", y="total",
            color_discrete_sequence=["#4f8ef7"],
            labels={"total": "Amount (৳)", "month": "Month"},
            text=monthly_total["total"].apply(lambda x: f"৳{x:,.0f}"),
        )
        fig.update_layout(
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117",
            font_color="#e0e4f0",
            margin=dict(l=0, r=0, t=0, b=0), height=360,
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No transaction data yet.")

# ── Spending by Card per Month ─────────────────────────────────────────────────
st.subheader("Monthly Spending by Card")
if monthly:
    df_stacked = pd.DataFrame([dict(r) for r in monthly])
    card_map = {c["card_id"]: c["card_name"] for c in db.get_cards()}
    df_stacked["card_name"] = df_stacked["card_id"].map(card_map).fillna(df_stacked["card_id"])
    fig2 = px.bar(
        df_stacked, x="month", y="total", color="card_name",
        barmode="stack",
        labels={"total": "Amount (৳)", "month": "Month", "card_name": "Card"},
    )
    fig2.update_layout(
        plot_bgcolor="#0f1117", paper_bgcolor="#0f1117",
        font_color="#e0e4f0", legend_title_text="Card",
        margin=dict(l=0, r=0, t=10, b=0), height=300,
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Utilization gauge per card ─────────────────────────────────────────────────
st.subheader("Credit Utilization per Card")
gauge_cols = st.columns(min(len(metrics), 3))
for i, m in enumerate(metrics):
    with gauge_cols[i % 3]:
        util = m["live_utilization"] * 100
        color = "#4ade80" if util < 30 else ("#fbbf24" if util < 50 else "#f87171")
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=util,
            number={"suffix": "%", "font": {"color": color}},
            title={"text": m["card_name"], "font": {"size": 12, "color": "#9ca3af"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#555"},
                "bar": {"color": color},
                "bgcolor": "#1a1d27",
                "steps": [
                    {"range": [0, 30],  "color": "#0d2010"},
                    {"range": [30, 50], "color": "#2d2000"},
                    {"range": [50, 100],"color": "#2d0000"},
                ],
                "threshold": {
                    "line": {"color": "#fff", "width": 2},
                    "thickness": 0.75, "value": 30,
                },
            },
        ))
        fig_g.update_layout(
            paper_bgcolor="#0f1117", font_color="#e0e4f0",
            height=200, margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_g, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  FULL CARD OVERVIEW TABLE
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Full Card Data Table", expanded=False):
    rows = []
    for m in metrics:
        rows.append({
            "Card": m["card_name"],
            "Bank": m["bank"],
            "Limit": utils.fmt_bdt(m["credit_limit"]),
            "Live Balance": utils.fmt_bdt(m["live_balance"]),
            "Stmt Balance": utils.fmt_bdt(m["statement_balance"]),
            "Stmt Due": utils.fmt_bdt(m["statement_balance_remaining"]),
            "Min Due": utils.fmt_bdt(m["minimum_due_remaining"]),
            "Available": utils.fmt_bdt(m["available_credit"]),
            "Utilization": utils.fmt_pct(m["live_utilization"]),
            "Points": m["reward_points"],
            "Waiver": f"{m['waiver_progress']*100:.0f}%",
            "Monthly EMI": utils.fmt_bdt(m["monthly_emi"]),
            "Days→Due": m["days_to_due"],
            "Days→Stmt": m["days_to_statement"],
            "Pay Status": m["payment_status"],
            "Priority": m["usage_priority"],
            "Eff. Score": m["efficiency_score"],
            "Next Action": m["next_action"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption(f"Refreshed: {today.strftime('%d %b %Y, %H:%M')}")
