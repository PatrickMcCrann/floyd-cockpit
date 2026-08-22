"""Floyd — Growth Decision Cockpit (Copperline, fictional).

Run:  streamlit run app.py

Three screens: Where we stand, Decision studio, The memo. All math is deterministic
and computed in model.py; the LLM writes narrative only, from computed metrics.
"""
from __future__ import annotations

import os

import streamlit as st

import charts
from data_loader import load_assumption_notes, load_assumptions, load_target
from integrity import check_plan_integrity, integrity_verdict
from model import (
    FY26_END,
    Scenario,
    actuals_plus_forecast,
    month_range,
    quarterly_fy27,
    revenue_bridge,
    run_forecast,
    scenario_metrics,
    summarize_actuals,
)
from narrative import NarrativeError, build_payload, generate_memo

st.set_page_config(page_title="Floyd — Growth Decision Cockpit", page_icon="◆", layout="wide")

SEVERITY_STYLE = {
    "critical": (charts.CRITICAL, "▲", "Critical"),
    "serious": (charts.SERIOUS, "▲", "Serious"),
    "warning": (charts.WARNING, "●", "Warning"),
}

st.markdown(
    f"""
    <style>
      .stApp {{ background: #f9f9f7; }}
      .flag-card {{
        border-left: 4px solid {charts.MUTED};
        background: {charts.SURFACE};
        border-radius: 6px;
        padding: 0.85rem 1.1rem;
        margin-bottom: 0.7rem;
        border-top: 1px solid rgba(11,11,11,0.06);
        border-right: 1px solid rgba(11,11,11,0.06);
        border-bottom: 1px solid rgba(11,11,11,0.06);
      }}
      .flag-head {{ font-weight: 650; color: {charts.INK}; font-size: 0.95rem; }}
      .flag-sev {{ font-size: 0.72rem; letter-spacing: .06em; text-transform: uppercase;
                   font-weight: 700; }}
      .flag-body {{ color: {charts.INK_2}; font-size: 0.88rem; margin-top: .35rem;
                    line-height: 1.5; }}
      .flag-moves {{ color: {charts.INK_2}; font-size: 0.85rem; margin: .5rem 0 0 0;
                     padding-left: 1.1rem; }}
      .flag-moves li {{ margin-bottom: .2rem; }}
      .verdict {{ font-size: 1.05rem; font-weight: 700; padding: .55rem .9rem;
                  border-radius: 6px; display: inline-block; margin-bottom: .8rem; }}
      .memo-body {{ background: {charts.SURFACE}; border-radius: 8px; padding: 1.6rem 2rem;
                    border: 1px solid rgba(11,11,11,0.08); }}
      .caption-note {{ color: {charts.MUTED}; font-size: 0.8rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def money(x: float, decimals: int = 2) -> str:
    if x is None:
        return "—"
    sign = "−" if x < 0 else ""
    v = abs(x)
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:,.{decimals}f}M"
    return f"{sign}${v / 1_000:,.0f}K"


def delta_money(x: float, decimals: int = 2) -> str:
    """Signed amount for st.metric deltas.

    Uses an ASCII hyphen deliberately: Streamlit reads the leading character to
    decide the arrow direction and colour, and does not recognise U+2212. A
    typographic minus here would paint a shortfall green.
    """
    v = abs(x)
    sign = "-" if x < 0 else "+"
    return f"{sign}${v / 1_000_000:,.{decimals}f}M" if v >= 1_000_000 else f"{sign}${v / 1_000:,.0f}K"


def esc_md(s: str) -> str:
    """Streamlit parses $...$ as LaTeX. Escape dollar signs in plain Markdown."""
    return s.replace("$", r"\$")


def esc_html(s: str) -> str:
    """Same problem inside unsafe_allow_html blocks, where a backslash would show.

    Use the HTML entity so no literal `$` reaches the Markdown/LaTeX parser.
    """
    return s.replace("$", "&#36;")


def months_label(m: float) -> str:
    if m == float("inf"):
        return "n/a — cash-flow positive"
    if m <= 0:
        return "Exhausted"
    return f"{m:.0f} months"


def render_flags(flags: list, verdict: str) -> None:
    color = charts.CRITICAL if "at risk" in verdict else (
        charts.WARNING if "qualified" in verdict else charts.GOOD
    )
    st.markdown(
        f'<div class="verdict" style="background:{color}1a;color:{color};'
        f'border:1px solid {color}55;">{verdict}</div>',
        unsafe_allow_html=True,
    )
    if not flags:
        st.markdown(
            '<div class="caption-note">No integrity rule fired on this scenario.</div>',
            unsafe_allow_html=True,
        )
        return
    for f in flags:
        color, icon, label = SEVERITY_STYLE.get(f.severity, (charts.MUTED, "●", f.severity))
        moves = "".join(f"<li>{esc_html(m)}</li>" for m in f.moves)
        st.markdown(
            f"""
            <div class="flag-card" style="border-left-color:{color};">
              <div class="flag-sev" style="color:{color};">{icon} {label}</div>
              <div class="flag-head">{esc_html(f.headline)}</div>
              <div class="flag-body">{esc_html(f.contradiction)}</div>
              <ul class="flag-moves">{moves}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --- Sidebar: navigation + levers -------------------------------------------

assumptions = load_assumptions()
notes = load_assumption_notes()
target = load_target()
defaults = Scenario.from_defaults()

st.sidebar.markdown("### ◆ Floyd")
st.sidebar.caption("Growth Decision Cockpit — Copperline (fictional, synthetic data)")

screen = st.sidebar.radio(
    "Screen",
    ["1 · Where we stand", "2 · Decision studio", "3 · The memo"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown("**Levers**")

if st.sidebar.button("Reset to plan of record", width="stretch"):
    for k in list(st.session_state.keys()):
        if k.startswith("lever_"):
            del st.session_state[k]
    st.session_state.pop("memo", None)
    st.rerun()

new_logos = st.sidebar.slider(
    "New logos / month", 0, 40, int(defaults.new_logos_per_month), key="lever_logos"
)
churn = st.sidebar.slider(
    "Monthly logo churn (%)", 0.0, 6.0, float(defaults.monthly_logo_churn_pct), 0.1,
    key="lever_churn",
)
nrr = st.sidebar.slider(
    "Net revenue retention (%)", 90, 140, int(defaults.net_revenue_retention_pct),
    key="lever_nrr",
)
price = st.sidebar.slider(
    "Price increase at renewal, from Oct 1 (%)", 0, 25, int(defaults.price_increase_pct),
    key="lever_price",
)

st.sidebar.markdown("**Sales capacity**")
ae_hires = st.sidebar.slider("New AE hires", 0, 12, int(defaults.new_ae_hires), key="lever_aes")
start_options = month_range("2026-09", "2027-06")
default_start_idx = start_options.index(defaults.new_ae_start)
ae_start = st.sidebar.selectbox(
    "AE start month", start_options, index=default_start_idx, key="lever_ae_start"
)
st.sidebar.caption(esc_md(
    f"{int(assumptions['ae_ramp_months'])}-month ramp to "
    f"{money(float(assumptions['ae_quota_net_new_mrr']), 0)}/mo quota."
))

st.sidebar.markdown("**Retention**")
haircut = st.sidebar.checkbox(
    esc_md(
        f"Haircut {money(float(assumptions['enterprise_renewals_at_risk_mrr']), 0)} at-risk "
        f"enterprise MRR (Nov)"
    ),
    value=defaults.at_risk_renewals_haircut,
    key="lever_haircut",
)

st.sidebar.markdown("**Acquisition**")
acquire = st.sidebar.checkbox(
    f"Acquire {target['target_name']}", value=defaults.acquire_brightpath, key="lever_acquire"
)
acq_price = st.sidebar.slider(
    "Purchase price ($M)", 4.0, 10.0, float(defaults.acquisition_price) / 1e6, 0.1,
    key="lever_acq_price", disabled=not acquire,
) * 1e6
acq_draw = st.sidebar.slider(
    "Funded from the undrawn line ($K)", 0, int(float(assumptions["debt_available"]) / 1e3),
    0, 50, key="lever_acq_draw", disabled=not acquire,
) * 1e3
if acquire:
    st.sidebar.caption(esc_md(
        f"Balance out of cash: {money(acq_price - acq_draw)}. Closes "
        f"{str(target['expected_close'])[:7]}."
    ))

st.sidebar.divider()
api_key = st.sidebar.text_input(
    "Anthropic API key",
    type="password",
    value="",
    help="Only needed for Screen 3. Leave blank to use the key configured for this "
         "deployment, or ANTHROPIC_API_KEY in the environment.",
)


def _deployment_key() -> str | None:
    """The key supplied by the host, if there is one.

    Streamlit Community Cloud puts whatever is set in its Secrets UI into
    st.secrets rather than the environment, so checking os.environ alone would
    leave a deployed app with no key. st.secrets raises when no secrets file
    exists at all, which is the normal local case, so the lookup is guarded.
    The environment fallback covers a local .env and any other host.
    """
    try:
        secret = st.secrets.get("ANTHROPIC_API_KEY")
        if secret:
            return str(secret)
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


effective_key = api_key or _deployment_key()
if effective_key and not api_key:
    st.sidebar.caption("Using the API key configured for this deployment.")

# --- Compute (deterministic, on every rerun) --------------------------------

scenario = Scenario(
    new_logos_per_month=float(new_logos),
    monthly_logo_churn_pct=float(churn),
    net_revenue_retention_pct=float(nrr),
    price_increase_pct=float(price),
    new_ae_hires=int(ae_hires),
    new_ae_start=ae_start,
    at_risk_renewals_haircut=bool(haircut),
    acquire_brightpath=bool(acquire),
    acquisition_price=float(acq_price),
    acquisition_debt_draw=float(acq_draw),
)

actuals = summarize_actuals()
fc = run_forecast(scenario)
metrics = scenario_metrics(scenario, fc)
flags = check_plan_integrity(scenario, fc, metrics)
verdict = integrity_verdict(flags)
series = actuals_plus_forecast(fc)

scenario_changed = scenario.as_dict() != defaults.as_dict()

# ============================================================================
# SCREEN 1 — Where we stand
# ============================================================================
if screen.startswith("1"):
    st.title("Where we stand")
    st.caption(
        f"Copperline · actuals through {actuals.last_month} · "
        f"{actuals.customers} customers · {actuals.headcount} heads"
    )

    run_rate_fy26 = metrics["fy26_exit_arr"]
    variance = run_rate_fy26 - actuals.fy26_target
    on_plan = variance >= 0
    status_color = charts.GOOD if on_plan else charts.SERIOUS
    status = (
        f"On plan for FY26 — the current run rate exits at {money(run_rate_fy26)} against the "
        f"{money(actuals.fy26_target)} board target, {money(abs(variance))} ahead."
        if on_plan
        else
        f"Off plan for FY26 — the current run rate exits at {money(run_rate_fy26)} against the "
        f"{money(actuals.fy26_target)} board target, {money(abs(variance))} short."
    )
    st.markdown(
        f'<div class="verdict" style="background:{status_color}1a;color:{status_color};'
        f'border:1px solid {status_color}55;">{esc_html(status)}</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ARR", money(actuals.arr), f"{actuals.arr_growth_mom_pct:+.2f}% MoM")
    c2.metric(
        "Cash", money(actuals.cash),
        f"−{money(actuals.net_burn_last, 0)} last month", delta_color="off",
    )
    c3.metric("Net burn (3-mo avg)", money(actuals.net_burn_trailing_3mo, 0))
    c4.metric(
        "Runway", f"{actuals.runway_months:.0f} months", "at current burn", delta_color="off"
    )
    c5.metric(
        "Gap to FY26 target", money(actuals.gap_to_fy26_target),
        f"{money(actuals.gap_to_fy26_target / 12, 0)} of MRR to close", delta_color="off",
    )

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**ARR trajectory**")
        st.plotly_chart(
            charts.arr_trajectory(series, actuals.fy26_target, float(assumptions["fy27_arr_target"])),
            use_container_width=True,
        )
    with right:
        st.markdown("**Cash against the covenant floor**")
        st.plotly_chart(
            charts.cash_and_covenant(series, float(assumptions["min_cash_covenant"])),
            use_container_width=True,
        )

    st.markdown("**Monthly net burn**")
    st.plotly_chart(charts.burn_chart(series), use_container_width=True)

    st.divider()
    st.markdown("### What the plan requires from here")
    q1, q2, q3 = st.columns(3)
    needed_mrr = actuals.gap_to_fy26_target / 12 / 4
    q1.metric(
        "Net-new MRR needed / month to hit FY26",
        money(needed_mrr, 0),
        f"{money(actuals.net_new_mrr_trailing_3mo, 0)} actual, trailing 3-mo",
        delta_color="off",
    )
    q2.metric(
        "Q4 net-new MRR the FY27 ramp requires",
        money(float(assumptions["q4_net_new_mrr_required"]), 0),
        f"{money(metrics['q4_2026_net_new_mrr'], 0)} modeled",
        delta_color="off",
    )
    q3.metric(
        "FY27 target", money(float(assumptions["fy27_arr_target"])),
        f"{money(metrics['fy27_exit_arr'])} modeled", delta_color="off",
    )

    st.divider()
    st.markdown("### Plan integrity")
    st.caption("Deterministic rules, evaluated on the plan of record. No lever has been touched.")
    render_flags(flags, verdict)

    with st.expander("Actuals detail — Jan–Aug 2026"):
        from data_loader import load_actuals
        st.dataframe(load_actuals(), width="stretch", hide_index=True)

# ============================================================================
# SCREEN 2 — Decision studio
# ============================================================================
elif screen.startswith("2"):
    st.title("Decision studio")
    st.caption(
        "Move a lever in the sidebar. Revenue, cash, runway, covenant headroom and the "
        "integrity check all recompute."
    )
    if scenario_changed:
        st.markdown(
            '<div class="caption-note">Scenario differs from the plan of record.</div>',
            unsafe_allow_html=True,
        )

    cov = metrics["covenant"]
    runway = metrics["runway_months_from_dec_2026"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "FY26 exit ARR", money(metrics["fy26_exit_arr"]),
        f"{delta_money(metrics['fy26_variance'])} vs target",
    )
    c2.metric(
        "FY27 exit ARR", money(metrics["fy27_exit_arr"]),
        f"{delta_money(metrics['fy27_variance'])} vs target",
    )
    c3.metric(
        "Cash, Dec 2026", money(metrics["dec_2026_cash"]),
        f"{money(metrics['avg_monthly_burn_q4_2026'], 0)}/mo burn", delta_color="off",
    )
    c4.metric("Runway from Dec 2026", months_label(runway))
    c5.metric(
        "Covenant headroom", money(cov["headroom"]),
        f"breach — trough {cov['trough_month']}" if cov["breach"]
        else f"trough {cov['trough_month']}",
        delta_color="off",
    )

    if cov["breach"]:
        st.error(esc_md(
            f"**Covenant breach.** Cash falls below the {money(cov['min_cash_covenant'])} floor "
            f"in {cov['first_breach_month']} and troughs at {money(cov['trough_cash'])} in "
            f"{cov['trough_month']} — {len(cov['breach_months'])} month(s) in breach."
        ))
    if metrics["cash_goes_negative_month"]:
        st.error(
            f"**Cash goes negative in {metrics['cash_goes_negative_month']}** under this scenario."
        )

    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown("**ARR — actuals and scenario forecast**")
        st.plotly_chart(
            charts.arr_trajectory(series, actuals.fy26_target, float(assumptions["fy27_arr_target"])),
            use_container_width=True,
        )
    with right:
        st.markdown("**Cash against the covenant floor**")
        st.plotly_chart(
            charts.cash_and_covenant(series, float(assumptions["min_cash_covenant"])),
            use_container_width=True,
        )

    st.markdown(f"**Revenue bridge — {actuals.last_month} ARR to {FY26_END} ARR**")
    st.plotly_chart(
        charts.revenue_bridge_chart(revenue_bridge(fc, FY26_END)), use_container_width=True
    )

    b1, b2 = st.columns(2)
    with b1:
        st.markdown("**Where forecast MRR comes from**")
        st.plotly_chart(charts.mrr_composition(fc), use_container_width=True)
    with b2:
        st.markdown("**FY27 by quarter**")
        q = quarterly_fy27(fc)
        st.plotly_chart(
            charts.quarterly_fy27_chart(q, float(assumptions["fy27_arr_target"])),
            use_container_width=True,
        )

    st.markdown("**Monthly forecast — Sep 2026 through Dec 2027**")
    show = fc[[
        "month", "customers", "mrr", "arr", "total_opex", "net_burn", "cash",
    ]].copy()
    show.columns = ["Month", "Customers", "MRR", "ARR", "Total opex", "Net burn", "Cash"]
    show["Customers"] = show["Customers"].round(0).astype(int)
    st.dataframe(
        show.style.format({
            "MRR": "${:,.0f}", "ARR": "${:,.0f}", "Total opex": "${:,.0f}",
            "Net burn": "${:,.0f}", "Cash": "${:,.0f}",
        }),
        width="stretch", hide_index=True, height=320,
    )

    with st.expander("FY27 quarterly detail"):
        qq = quarterly_fy27(fc)
        qq.columns = ["Quarter", "Exit ARR", "Revenue", "Total opex", "Net burn", "Ending cash"]
        st.dataframe(
            qq.style.format({c: "${:,.0f}" for c in qq.columns if c != "Quarter"}),
            width="stretch", hide_index=True,
        )

    st.divider()
    st.markdown("### Plan integrity")
    render_flags(flags, verdict)

# ============================================================================
# SCREEN 3 — The memo
# ============================================================================
else:
    st.title("The memo")
    st.caption(
        "Written by Claude from the computed metrics on the left. The model writes; "
        "it does not calculate."
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "FY26 exit ARR", money(metrics["fy26_exit_arr"]),
        f"{delta_money(metrics['fy26_variance'])} vs target",
    )
    m2.metric(
        "FY27 exit ARR", money(metrics["fy27_exit_arr"]),
        f"{delta_money(metrics['fy27_variance'])} vs target",
    )
    m3.metric("Covenant headroom", money(metrics["covenant"]["headroom"]))
    m4.metric("Integrity flags", str(len(flags)), verdict.split(": ")[-1], delta_color="off")

    st.divider()
    render_flags(flags, verdict)
    st.divider()

    payload = build_payload(
        actuals, scenario, metrics, flags,
        quarterly_fy27(fc).to_dict(orient="records"),
        revenue_bridge(fc, FY26_END),
    )
    fingerprint = str(scenario.as_dict())

    col_a, col_b = st.columns([1, 3])
    with col_a:
        generate = st.button("Generate memo", type="primary", width="stretch")
    with col_b:
        if st.session_state.get("memo_fingerprint") not in (None, fingerprint):
            st.warning("Scenario changed since this memo was written. Regenerate to update it.")

    if generate:
        with st.spinner("Floyd is writing the memo…"):
            try:
                st.session_state["memo"] = generate_memo(payload, effective_key or None)
                st.session_state["memo_fingerprint"] = fingerprint
            except NarrativeError as exc:
                st.error(str(exc))

    memo = st.session_state.get("memo")
    if memo:
        with st.container(border=True):
            st.markdown(memo)
        st.download_button(
            "Download memo (Markdown)", memo,
            file_name=f"copperline-cfo-memo-{actuals.last_month}.md",
            mime="text/markdown",
        )
    else:
        st.info(
            "Press **Generate memo**. The memo is written for the scenario currently set in the "
            "sidebar and regenerates whenever you change it."
        )

    with st.expander("The structured JSON handed to the model"):
        st.caption(
            "The model receives only these computed results — no raw data, no formulas. "
            "This is the full input, verbatim."
        )
        st.json(payload)

    with st.expander("System prompt"):
        from narrative import SYSTEM_PROMPT
        st.code(SYSTEM_PROMPT, language="text")

st.sidebar.divider()
st.sidebar.caption(
    "Fictional company. Synthetic data. Not financial, accounting, tax, legal or "
    "investment advice."
)
