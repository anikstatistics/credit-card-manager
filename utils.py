"""Shared UI utilities, CSS, and formatters."""
import streamlit as st


CARD_CSS = """
<style>
/* ── Metric cards ── */
div[data-testid="metric-container"] {
    background: #1a1d27;
    border: 1px solid #2d3148;
    border-radius: 10px;
    padding: 14px 18px;
}
/* ── Status colours ── */
.badge-safe     { background:#1a3d2b; color:#4ade80; border-radius:6px; padding:2px 10px; font-size:.8rem; font-weight:600; }
.badge-caution  { background:#3d3010; color:#fbbf24; border-radius:6px; padding:2px 10px; font-size:.8rem; font-weight:600; }
.badge-urgent   { background:#3d1010; color:#f87171; border-radius:6px; padding:2px 10px; font-size:.8rem; font-weight:600; }
.badge-info     { background:#102040; color:#60a5fa; border-radius:6px; padding:2px 10px; font-size:.8rem; font-weight:600; }
.badge-neutral  { background:#222; color:#aaa; border-radius:6px; padding:2px 10px; font-size:.8rem; font-weight:600; }
/* ── Card summary tile ── */
.card-tile {
    background: #1a1d27;
    border-radius: 12px;
    border-left: 4px solid #4f8ef7;
    padding: 16px 18px;
    margin-bottom: 10px;
    min-height: 180px;
}
.card-tile.safe   { border-left-color: #4ade80; }
.card-tile.caution{ border-left-color: #fbbf24; }
.card-tile.urgent { border-left-color: #f87171; }
.card-tile h4 { margin: 0 0 4px 0; font-size: 1rem; color: #e0e4f0; }
.card-tile .bank  { font-size:.75rem; color:#888; margin-bottom:10px; }
.card-tile .row   { display:flex; justify-content:space-between; font-size:.82rem; margin:3px 0; }
.card-tile .label { color: #9ca3af; }
.card-tile .value { color: #e0e4f0; font-weight:600; }
.card-tile .action-box {
    margin-top: 10px;
    background: #111420;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: .8rem;
    color: #93c5fd;
}
/* ── Progress bar ── */
.prog-wrap { background:#2a2d3a; border-radius:6px; height:8px; width:100%; margin:4px 0; }
.prog-fill  { height:8px; border-radius:6px; }
/* ── Section header ── */
.section-header {
    font-size: 1rem;
    font-weight: 700;
    color: #9ca3af;
    letter-spacing: .08em;
    text-transform: uppercase;
    border-bottom: 1px solid #2d3148;
    padding-bottom: 6px;
    margin: 20px 0 12px 0;
}
/* ── Best-card banner ── */
.best-card-banner {
    background: linear-gradient(135deg, #1a2744 0%, #112234 100%);
    border: 1px solid #2d5a9e;
    border-radius: 10px;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 16px;
}
.best-card-banner .icon  { font-size: 2rem; }
.best-card-banner .title { font-size: .8rem; color:#60a5fa; font-weight:600; letter-spacing:.05em; text-transform:uppercase; }
.best-card-banner .name  { font-size: 1.15rem; color:#e0e4f0; font-weight:700; }
</style>
"""


def inject_css():
    st.markdown(CARD_CSS, unsafe_allow_html=True)


def fmt_bdt(amount: float) -> str:
    return f"৳{amount:,.2f}"


def fmt_pct(ratio: float) -> str:
    return f"{ratio * 100:.0f}%"


def progress_bar_html(ratio: float, color: str = "#4f8ef7") -> str:
    pct = min(100, max(0, ratio * 100))
    return (
        f'<div class="prog-wrap">'
        f'<div class="prog-fill" style="width:{pct:.1f}%;background:{color};"></div>'
        f'</div>'
    )


def status_color(status: str) -> str:
    s = status.lower()
    if any(x in s for x in ("safe", "done", "secured", "completed", "free", "on track")):
        return "#4ade80"
    if any(x in s for x in ("caution", "upcoming", "almost", "near")):
        return "#fbbf24"
    if any(x in s for x in ("urgent", "overdue", "due soon")):
        return "#f87171"
    return "#9ca3af"


def tile_class(usage_priority: str) -> str:
    p = usage_priority.lower()
    if p == "safe":
        return "safe"
    if p == "caution":
        return "caution"
    return "urgent"


def card_tile_html(m: dict) -> str:
    util_color = "#4ade80" if m["live_utilization"] < 0.3 else (
        "#fbbf24" if m["live_utilization"] < 0.5 else "#f87171"
    )
    waiver_color = (
        "#4ade80" if m["waiver_progress"] >= 1.0 else
        "#fbbf24" if m["waiver_progress"] >= 0.5 else "#f87171"
    )
    util_pct = m["live_utilization"] * 100
    waiver_pct = m["waiver_progress"] * 100
    tile_cls = tile_class(m["usage_priority"])

    stmt_due_str = (
        fmt_bdt(m["statement_balance_remaining"])
        if m["statement_balance_remaining"] > 0
        else "Paid"
    )
    due_str = (
        f"{m['days_to_due']}d" if m["days_to_due"] > 0 else "Done"
    )

    return f"""
    <div class="card-tile {tile_cls}">
        <h4>💳 {m['card_name']}</h4>
        <div class="bank">{m['bank']}</div>
        <div class="row">
            <span class="label">Limit</span>
            <span class="value">{fmt_bdt(m['credit_limit'])}</span>
        </div>
        <div class="row">
            <span class="label">Live Balance</span>
            <span class="value">{fmt_bdt(m['live_balance'])}</span>
        </div>
        <div class="row">
            <span class="label">Utilization</span>
            <span class="value" style="color:{util_color}">{util_pct:.0f}%</span>
        </div>
        {progress_bar_html(m['live_utilization'], util_color)}
        <div class="row" style="margin-top:6px">
            <span class="label">Stmt Due</span>
            <span class="value">{stmt_due_str}</span>
        </div>
        <div class="row">
            <span class="label">Waiver</span>
            <span class="value" style="color:{waiver_color}">{waiver_pct:.0f}%
            {"✓" if m['waiver_progress'] >= 1.0 else ""}</span>
        </div>
        {progress_bar_html(m['waiver_progress'], waiver_color)}
        <div class="action-box">→ {m['next_action']}</div>
    </div>
    """


def page_config(title: str = "Credit Card Manager"):
    st.set_page_config(
        page_title=title,
        page_icon="💳",
        layout="wide",
        initial_sidebar_state="expanded",
    )
