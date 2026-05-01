"""Rewards – points balance, redemption history."""
import streamlit as st
import pandas as pd
from datetime import date

import db, calc, utils

utils.page_config("Rewards")
db.init_db()
utils.inject_css()

st.title("⭐ Rewards & Points")

cards = db.get_cards(active_only=True)
if not cards:
    st.info("No cards yet.")
    st.stop()

# ── Points balance per card ────────────────────────────────────────────────────
st.markdown('<div class="section-header">POINTS BALANCE</div>', unsafe_allow_html=True)

cols = st.columns(min(len(cards), 3))
total_pts = 0
for i, card in enumerate(cards):
    card = dict(card)
    pts = calc.get_reward_points(card["card_id"], card["points_divisor"])
    total_pts += pts
    earned = calc.get_total_points_earned(card["card_id"], card["points_divisor"])
    redeemed = db.get_redeemed_points(card["card_id"])
    with cols[i % 3]:
        st.markdown(
            f"""<div style="background:#1a1d27;border-radius:10px;padding:14px 16px;
            border-left:4px solid #4f8ef7;margin-bottom:8px;">
            <div style="font-size:.8rem;color:#9ca3af;">{card['card_name']}</div>
            <div style="font-size:1.4rem;font-weight:700;color:#fbbf24;">{pts:,} pts</div>
            <div style="font-size:.75rem;color:#9ca3af;margin-top:4px;">
            Earned: {earned:,} · Redeemed: {redeemed:,}<br>
            Divisor: ৳{card['points_divisor']:.0f} per point</div>
            </div>""",
            unsafe_allow_html=True,
        )

st.metric("Total Reward Points (all cards)", f"{total_pts:,}")

# ── Redeem / Adjust form ───────────────────────────────────────────────────────
with st.expander("➕ Record Redemption / Adjustment", expanded=False):
    with st.form("reward_form"):
        c1, c2 = st.columns(2)
        with c1:
            card_opts = {c["card_id"]: f"{c['card_name']} ({c['card_id']})" for c in cards}
            card_id = st.selectbox("Card", list(card_opts.keys()),
                format_func=lambda k: card_opts[k])
            reward_date = st.date_input("Date", value=date.today())
        with c2:
            points_redeemed = st.number_input(
                "Points Redeemed", min_value=0, step=100,
                help="Positive = redemption (reduces balance)",
            )
            adjustment = st.number_input(
                "Adjustment (bonus/correction)", step=1,
                help="Positive = bonus points added; negative = correction",
            )
            notes = st.text_input("Notes")

        submitted = st.form_submit_button("Save")
        if submitted:
            rw_id = db.next_id("RWD", "rewards", "reward_id")
            db.upsert_reward({
                "reward_id": rw_id,
                "date": str(reward_date),
                "card_id": card_id,
                "points_redeemed": int(points_redeemed),
                "adjustment": int(adjustment),
                "notes": notes.strip(),
            })
            st.success(f"Saved {rw_id}.")
            st.rerun()

# ── Redemption history ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">REDEMPTION HISTORY</div>', unsafe_allow_html=True)
card_map = {c["card_id"]: c["card_name"] for c in db.get_cards()}
rewards = db.get_rewards()

if rewards:
    rows = [{
        "ID": r["reward_id"],
        "Date": r["date"],
        "Card": card_map.get(r["card_id"], r["card_id"]),
        "Redeemed": r["points_redeemed"],
        "Adjustment": r["adjustment"],
        "Net": r["points_redeemed"] - r["adjustment"],
        "Notes": r["notes"] or "",
    } for r in rewards if r["reward_id"]]

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        with st.expander("Delete a record"):
            del_id = st.text_input("Reward ID to delete")
            if st.button("Delete") and del_id:
                db.delete_reward(del_id.strip().upper())
                st.rerun()
    else:
        st.info("No redemption records yet.")
else:
    st.info("No redemption records yet.")

# ── Points earned per card per month ──────────────────────────────────────────
st.markdown('<div class="section-header">POINTS EARNED BY MONTH</div>', unsafe_allow_html=True)

monthly = db.get_monthly_spending()
if monthly:
    import plotly.express as px
    card_pts_rows = []
    for row in monthly:
        c = db.get_card(row["card_id"])
        if not c:
            continue
        pts = calc.calc_points(row["total"], c["points_divisor"])
        card_pts_rows.append({
            "month": row["month"],
            "card": c["card_name"],
            "points": pts,
        })
    if card_pts_rows:
        import pandas as pd_
        df = pd_.DataFrame(card_pts_rows)
        fig = px.bar(df, x="month", y="points", color="card", barmode="stack",
            labels={"points": "Points Earned", "month": "Month", "card": "Card"})
        fig.update_layout(
            plot_bgcolor="#0f1117", paper_bgcolor="#0f1117",
            font_color="#e0e4f0", height=280,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
