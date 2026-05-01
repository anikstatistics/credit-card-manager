"""Category Management – keyword→category mapping."""
import streamlit as st
import pandas as pd

import db, utils

utils.page_config("Categories")
db.init_db()
utils.inject_css()

st.title("🏷️ Categories")
st.caption("Map merchant keywords to transaction types and categories for auto-fill.")

TRANSACTION_TYPES = ["Purchase", "Fee", "Insurance", "Cash Advance", "Refund"]
CATEGORY_TYPES    = ["Spending", "Financial"]

# ── Add / Edit ─────────────────────────────────────────────────────────────────
with st.expander("➕ Add / Edit Keyword Mapping", expanded=False):
    cats = db.get_categories()
    keywords = [c["keyword"] for c in cats]

    mode = st.radio("Mode", ["New Mapping", "Edit Existing"], horizontal=True)
    edit_cat = None
    if mode == "Edit Existing" and keywords:
        sel_kw = st.selectbox("Keyword to edit", keywords)
        edit_cat = next((c for c in cats if c["keyword"] == sel_kw), None)

    with st.form("cat_form"):
        defaults = dict(edit_cat) if edit_cat else {}
        c1, c2 = st.columns(2)
        with c1:
            keyword = st.text_input(
                "Keyword (merchant name or partial)",
                value=defaults.get("keyword", ""),
                disabled=(mode == "Edit Existing"),
            )
            txn_type = st.selectbox(
                "Transaction Type",
                TRANSACTION_TYPES,
                index=TRANSACTION_TYPES.index(defaults.get("transaction_type", "Purchase")),
            )
        with c2:
            category = st.text_input("Category", value=defaults.get("category", ""))
            cat_type = st.selectbox(
                "Category Type",
                CATEGORY_TYPES,
                index=CATEGORY_TYPES.index(defaults.get("category_type", "Spending")),
            )

        submitted = st.form_submit_button("Save")
        if submitted:
            kw = keyword.strip() if mode == "New Mapping" else (edit_cat["keyword"] if edit_cat else keyword.strip())
            if not kw or not category:
                st.error("Keyword and Category are required.")
            else:
                db.upsert_category({
                    "keyword": kw,
                    "transaction_type": txn_type,
                    "category": category.strip(),
                    "category_type": cat_type,
                })
                st.success(f"Saved mapping for '{kw}'.")
                st.rerun()

# ── Search & list ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">ALL MAPPINGS</div>', unsafe_allow_html=True)

search = st.text_input("Search keyword", placeholder="Type to filter…")
cats = db.get_categories()

if search:
    cats = [c for c in cats if search.lower() in c["keyword"].lower() or
            search.lower() in c["category"].lower()]

if cats:
    st.caption(f"{len(cats)} mappings")
    rows = [{
        "Keyword": c["keyword"],
        "Transaction Type": c["transaction_type"],
        "Category": c["category"],
        "Category Type": c["category_type"],
    } for c in cats]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

    with st.expander("Delete a mapping"):
        del_kw = st.text_input("Keyword to delete (exact match)")
        if st.button("Delete") and del_kw:
            db.delete_category(del_kw.strip())
            st.success(f"Deleted '{del_kw}'.")
            st.rerun()
else:
    st.info("No mappings found." if search else "No category mappings yet.")

# ── Spending by Category Type ──────────────────────────────────────────────────
with st.expander("Category Spending Summary", expanded=False):
    import plotly.express as px
    cat_rows = db.get_spending_by_category()
    if cat_rows:
        import pandas as pd_
        df = pd_.DataFrame([dict(r) for r in cat_rows])
        fig = px.pie(df[df["total"] > 0], values="total", names="category",
            title="All-time Spending by Category",
            color_discrete_sequence=px.colors.sequential.Blues_r)
        fig.update_layout(
            paper_bgcolor="#0f1117", font_color="#e0e4f0", height=400,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No transaction data yet.")
