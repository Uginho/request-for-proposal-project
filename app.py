import os

import streamlit as st

from src.agents.distributor_finder import run_distributor_finder
from src.agents.menu_parser import run_menu_parser
from src.agents.rfp_emailer import generate_rfp_drafts, send_selected
from src.agents.usda_pricing import run_usda_pricing
from src.db.models import (
    get_all_dishes,
    get_all_distributors,
    get_all_ingredient_pricing,
    get_all_rfp_emails,
    get_dish_ingredients,
    init_db,
    pricing_already_fetched,
)

init_db()  # ensures tables exist on fresh installs before any reads

MENU_PDF = os.path.join(os.path.dirname(__file__), "data/menu.pdf")

st.set_page_config(page_title="Pablo y Pablo — RFP System", layout="wide")
st.title("Automated Request for Proposal System")
st.caption("Restaurant: Pablo y Pablo")
st.caption("Located: 1605 N 34th St · Wallingford · Seattle, WA")

st.divider()
st.write("Welcome — Generate Your RFP Now.")
st.divider()

# ---------------------------------------------------------------------------
# Step 1: Menu → Recipes & Ingredients
# ---------------------------------------------------------------------------
st.header("Step 1: Menu → Recipes & Ingredients")
st.caption("Collects Pablo y Pablo's Lunch/Dinner menu and extracts ingredients")

if st.button("Parse Menu", type="primary"):
    progress_bar = st.progress(0, text="Starting...")
    status = st.empty()

    def update_progress(current, total, dish_name):
        pct = int((current / total) * 100)
        progress_bar.progress(pct, text=f"Parsing dish {current + 1} of {total}: {dish_name}")
        status.caption(f"Processing: {dish_name}")

    with st.spinner(""):
        results = run_menu_parser(MENU_PDF, progress_callback=update_progress)

    progress_bar.progress(100, text="Done!")
    status.empty()

    failed = [r for r in results if "error" in r]
    succeeded = [r for r in results if "ingredients" in r]

    st.success(f"Parsed {len(succeeded)} dishes successfully.")
    if failed:
        st.warning(f"{len(failed)} dish(es) failed to parse: {', '.join(r['dish'] for r in failed)}")

# ---------------------------------------------------------------------------
# Step 1 results — always show if DB has data
# ---------------------------------------------------------------------------
dishes = get_all_dishes()

if dishes:
    st.subheader(f"Stored Dishes ({len(dishes)})")

    categories = sorted(set(d["category"] for d in dishes))
    for category in categories:
        category_dishes = [d for d in dishes if d["category"] == category]
        with st.expander(f"{category.replace('_', ' ').title()} ({len(category_dishes)} dishes)"):
            for dish in category_dishes:
                st.markdown(f"**{dish['name'].title()}**")
                ingredients = get_dish_ingredients(dish["id"])
                if ingredients:
                    for ing in ingredients:
                        qty = f"{ing['quantity']} {ing['unit']}" if ing["quantity"] else "–"
                        notes = f" *({ing['notes']})*" if ing.get("notes") else ""
                        st.write(f"  • {ing['name']}: {qty}{notes}")
                else:
                    st.caption("  No ingredients stored.")
                st.write("")

st.divider()

# ---------------------------------------------------------------------------
# Step 2: Ingredient Pricing Trends (USDA API)
# ---------------------------------------------------------------------------
st.header("Step 2: Ingredients Current Market Price")
st.caption("Calls USDA API to collect current pricing by ingredient. Broken down into 3 categories: Ingredient price per pound, priced packages, and a list of ingredients not accounted for in USDA database")

dishes = get_all_dishes()
if not dishes:
    st.info("Complete Step 1 first to populate ingredients before fetching pricing.")
else:
    if st.button("Fetch USDA Pricing", type="primary"):
        progress_bar2 = st.progress(0, text="Starting...")
        status2 = st.empty()

        def update_progress2(current, total, name):
            pct = int((current / total) * 100) if total else 0
            progress_bar2.progress(pct, text=f"Pricing {current + 1} of {total}: {name}")
            status2.caption(f"Looking up: {name}")

        with st.spinner(""):
            pricing_results = run_usda_pricing(progress_callback=update_progress2)

        progress_bar2.progress(100, text="Done!")
        status2.empty()

        found = [r for r in pricing_results if r.get("status") == "found"]
        no_data = [r for r in pricing_results if r.get("status") == "no_data"]
        not_found = [r for r in pricing_results if r.get("status") == "not_found"]

        st.success(f"Pricing fetched: {len(found)} priced · {len(not_found)} not found in report · {len(no_data)} no USDA equivalent")

    # Always show pricing table if data exists
    pricing = get_all_ingredient_pricing()
    if pricing:
        st.subheader(f"Ingredient Pricing ({len(pricing)} ingredients)")
        st.caption("Source: USDA AMS Market News · Los Angeles Terminal Market (closest active Pacific market to Seattle)")

        per_lb     = [p for p in pricing if p["price_per_lb"] is not None]
        pkg_only   = [p for p in pricing if p["price_per_lb"] is None and p["original_price"] is not None]
        no_data    = [p for p in pricing if p["original_price"] is None]

        # ── Normalized to per-lb ───────────────────────────────────────────
        if per_lb:
            with st.expander(f"Normalized Price per Pound ({len(per_lb)})", expanded=True):
                col1, col2, col3 = st.columns([3, 3, 2])
                col1.markdown("**Ingredient**")
                col2.markdown("**USDA Raw Price · Package**")
                col3.markdown("**Price per lb**")
                st.divider()
                for p in sorted(per_lb, key=lambda x: x["name"]):
                    col1, col2, col3 = st.columns([3, 3, 2])
                    col1.write(p["name"])
                    col2.caption(f"${p['original_price']} · {p['original_unit']}")
                    col3.write(f"**${p['price_per_lb']:.4f}**")

        # ── Has price but package unit couldn't be normalized ─────────────
        if pkg_only:
            with st.expander(f"USDA Price per Package ({len(pkg_only)})"):
                col1, col2, col3 = st.columns([3, 3, 2])
                col1.markdown("**Ingredient**")
                col2.markdown("**Package**")
                col3.markdown("**USDA Price**")
                st.divider()
                for p in sorted(pkg_only, key=lambda x: x["name"]):
                    col1, col2, col3 = st.columns([3, 3, 2])
                    col1.write(p["name"])
                    col2.caption(p["original_unit"] or "—")
                    col3.write(f"**${p['original_price']}**")

        # ── No USDA data ───────────────────────────────────────────────────
        if no_data:
            with st.expander(f"No USDA Data Found ({len(no_data)})"):
                names = sorted(p["name"] for p in no_data)
                # Display as a compact multi-column list
                cols = st.columns(3)
                for i, name in enumerate(names):
                    cols[i % 3].write(f"• {name}")

st.divider()

# ---------------------------------------------------------------------------
# Step 3: Find Local Distributors
# ---------------------------------------------------------------------------
st.header("Step 3: List Local Distributors")
st.caption("Identifies Seattle-area food distributors (broadline & specialty) and persists contact details to DB")

if st.button("List Distributors", type="primary"):
    with st.spinner("Gathering distributor data..."):
        run_distributor_finder()
    st.success("Distributors found, see info below.")

distributors = get_all_distributors()
if distributors:
    st.subheader(f"Distributors ({len(distributors)})")
    for d in distributors:
        with st.expander(f"{d['name']} — {d.get('specialty', '')}"):
            col1, col2 = st.columns(2)
            with col1:
                if d.get("address"):
                    st.write(f"**Address:** {d['address']}, {d['city']}, {d['state']}")
                if d.get("phone"):
                    st.write(f"**Phone:** {d['phone']}")
                if d.get("email"):
                    st.write(f"**Email:** {d['email']}")
            with col2:
                if d.get("website"):
                    st.write(f"**Website:** {d['website']}")
                if d.get("notes"):
                    st.caption(d["notes"])

st.divider()

# ---------------------------------------------------------------------------
# Step 4: Send RFP Emails
# ---------------------------------------------------------------------------
st.header("Step 4: Send RFP Emails")
st.caption("Matches ingredients to distributor specialties, generates draft emails for review, then sends only to selected distributors.")

if not get_all_distributors():
    st.info("Complete Step 3 first to populate distributors.")
elif not get_all_dishes():
    st.info("Complete Step 1 first to populate ingredients.")
else:
    if "rfp_drafts" not in st.session_state:
        st.session_state.rfp_drafts = []

    if st.button("Generate RFP Emails", type="primary"):
        with st.spinner("Matching ingredients to distributor specialties..."):
            st.session_state.rfp_drafts = generate_rfp_drafts()
        st.success(f"Generated {len(st.session_state.rfp_drafts)} draft emails — review and select below.")

    if st.session_state.rfp_drafts:
        st.subheader("Review & Select")
        st.caption("Expand each card to preview the email. Check the distributors you want to send to, then click Send.")

        selected_drafts = []
        for draft in st.session_state.rfp_drafts:
            col_check, col_content = st.columns([1, 11])
            with col_check:
                checked = st.checkbox(
                    "Select",
                    key=f"sel_{draft['distributor_id']}",
                    label_visibility="collapsed",
                )
            with col_content:
                with st.expander(
                    f"{draft['distributor_name']} — {draft['specialty']} · {len(draft['matched_ingredients'])} ingredients"
                ):
                    st.caption(f"To: {draft['to_email']}")
                    st.caption(f"Subject: {draft['subject']}")
                    st.text_area(
                        "Preview",
                        draft["body"],
                        height=220,
                        disabled=True,
                        key=f"preview_{draft['distributor_id']}",
                        label_visibility="collapsed",
                    )
            if checked:
                selected_drafts.append(draft)

        st.write("")
        if selected_drafts:
            if st.button(f"Send {len(selected_drafts)} Selected Email(s)", type="primary"):
                with st.spinner("Sending..."):
                    send_results = send_selected(selected_drafts)
                sent_ok = [r for r in send_results if r["status"] == "sent"]
                failed_r = [r for r in send_results if r["status"] != "sent"]
                st.success(f"Sent {len(sent_ok)} email(s) successfully.")
                if failed_r:
                    for f in failed_r:
                        st.error(f"{f['distributor']}: {f['status']}")
        else:
            st.caption("Select at least one distributor above to enable sending.")

    # Always show email log
    rfp_emails = get_all_rfp_emails()
    if rfp_emails:
        st.subheader(f"Email Log ({len(rfp_emails)})")
        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        col1.markdown("**Distributor**")
        col2.markdown("**Sent To**")
        col3.markdown("**Status**")
        col4.markdown("**Sent At**")
        st.divider()
        for e in rfp_emails:
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            col1.write(e["distributor_name"])
            col2.caption(e["to_email"])
            icon = "✅" if e["status"] == "sent" else ("📝" if e["status"] == "draft" else "❌")
            col3.write(f"{icon} {e['status']}")
            col4.caption(e["sent_at"][:16] if e["sent_at"] else "—")
