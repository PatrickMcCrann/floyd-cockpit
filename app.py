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

show_levers = not screen.startswith("1")

# Lever values are mirrored into `val_*` keys because Screen 1 deliberately does
# not render the widgets, and Streamlit discards widget state for any widget it
# does not instantiate on a run. The mirror keeps a scenario intact while the
# user reads the baseline and comes back.
LEVER_DEFAULTS = {
    "logos": int(defaults.new_logos_per_month),
    "churn": float(defaults.monthly_logo_churn_pct),
    "nrr": int(defaults.net_revenue_retention_pct),
    "price": int(defaults.price_increase_pct),
    "aes": int(defaults.new_ae_hires),
    "ae_start": defaults.new_ae_start,
    "haircut": bool(defaults.at_risk_renewals_haircut),
    "acquire": bool(defaults.acquire_brightpath),
    "acq_price_m": float(defaults.acquisition_price) / 1e6,
    "acq_draw_k": 0,
}


def lv(name):
    """Current value of a lever, whether or not its widget is on screen."""
    return st.session_state.get(f"val_{name}", LEVER_DEFAULTS[name])


def keep(name, value):
    st.session_state[f"val_{name}"] = value
    return value


if show_levers:
    st.sidebar.divider()
    st.sidebar.markdown("**Levers**")

    if st.sidebar.button("Reset to plan of record", width="stretch"):
        for k in list(st.session_state.keys()):
            if k.startswith(("lever_", "val_")):
                del st.session_state[k]
        st.session_state.pop("memo", None)
        st.rerun()

    st.sidebar.markdown("_Current trajectory_")
    keep("logos", st.sidebar.slider(
        "New logos / month", 0, 40, lv("logos"), key="lever_logos"))
    keep("churn", st.sidebar.slider(
        "Monthly logo churn (%)", 0.0, 6.0, lv("churn"), 0.1, key="lever_churn"))
    keep("nrr", st.sidebar.slider(
        "Net revenue retention (%)", 90, 140, lv("nrr"), key="lever_nrr"))
    keep("price", st.sidebar.slider(
        "Price increase at renewal, from Oct 1 (%)", 0, 25, lv("price"), key="lever_price"))

    st.sidebar.markdown("_Sales capacity_")
    keep("aes", st.sidebar.slider("New AE hires", 0, 12, lv("aes"), key="lever_aes"))
    start_options = month_range("2026-09", "2027-06")
    keep("ae_start", st.sidebar.selectbox(
        "AE start month", start_options,
        index=start_options.index(lv("ae_start")), key="lever_ae_start"))
    st.sidebar.caption(esc_md(
        f"{int(assumptions['ae_ramp_months'])}-month ramp to "
        f"{money(float(assumptions['ae_quota_net_new_mrr']), 0)}/mo quota. A rep books "
        f"nothing in month 1, so a start date late in the year contributes nothing to FY26."
    ))

    st.sidebar.markdown("_Retention_")
    keep("haircut", st.sidebar.checkbox(
        esc_md(
            f"Haircut {money(float(assumptions['enterprise_renewals_at_risk_mrr']), 0)} at-risk "
            f"enterprise MRR (Nov)"
        ),
        value=lv("haircut"), key="lever_haircut"))

    st.sidebar.markdown("_Acquisition_")
    keep("acquire", st.sidebar.checkbox(
        f"Acquire {target['target_name']}", value=lv("acquire"), key="lever_acquire"))
    keep("acq_price_m", st.sidebar.slider(
        "Purchase price ($M)", 4.0, 10.0, lv("acq_price_m"), 0.1,
        key="lever_acq_price", disabled=not lv("acquire")))
    keep("acq_draw_k", st.sidebar.slider(
        "Funded from the undrawn line ($K)", 0, int(float(assumptions["debt_available"]) / 1e3),
        lv("acq_draw_k"), 50, key="lever_acq_draw", disabled=not lv("acquire")))
    if lv("acquire"):
        st.sidebar.caption(esc_md(
            f"Balance out of cash: {money(lv('acq_price_m') * 1e6 - lv('acq_draw_k') * 1e3)}. "
            f"Closes {str(target['expected_close'])[:7]}."
        ))
else:
    st.sidebar.divider()
    st.sidebar.caption(
        "This screen is the fixed baseline — the plan of record, before any decision. "
        "The levers live in the Decision studio."
    )

new_logos, churn, nrr, price = lv("logos"), lv("churn"), lv("nrr"), lv("price")
ae_hires, ae_start = lv("aes"), lv("ae_start")
haircut, acquire = lv("haircut"), lv("acquire")
acq_price = lv("acq_price_m") * 1e6
acq_draw = lv("acq_draw_k") * 1e3

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

# The plan of record, always. Screen 1 reports this and nothing else, so the
# baseline cannot move while the reader is looking at it; Screen 2 draws it
# behind the active scenario as the do-nothing reference.
if scenario_changed:
    por_fc = run_forecast(defaults)
    por_metrics = scenario_metrics(defaults, por_fc)
    por_flags = check_plan_integrity(defaults, por_fc, por_metrics)
    por_verdict = integrity_verdict(por_flags)
    por_series = actuals_plus_forecast(por_fc)
else:
    por_fc, por_metrics, por_flags = fc, metrics, flags
    por_verdict, por_series = verdict, series

# ============================================================================
# SCREEN 1 — Where we stand
# ============================================================================
if screen.startswith("1"):
    st.title("Where we stand")
    st.caption(
        f"Copperline · actuals through {actuals.last_month} · "
        f"{actuals.customers} customers · {actuals.headcount} heads"
    )

    st.markdown(esc_md(
        "This is a forecasting tool built by Copperline's CFO for the leadership team "
        "and the board. Eight months of FY26 actuals are on the books; September "
        "through December remain, plus the FY27 plan to set. The board wants "
        f"{money(actuals.fy26_target)} exit ARR this year and "
        f"{money(float(assumptions['fy27_arr_target']))} next — roughly 49% growth — and the "
        "CEO wants to accelerate to get there, by hiring account executives, by acquiring "
        f"{target['target_name']}, or both.\n\n"
        "**This page is the fixed starting point: the plan of record, before any decision.** "
        "Nothing here moves. The Decision studio is where you change it, and the memo is "
        "where you publish the result."
    ))

    run_rate_fy26 = por_metrics["fy26_exit_arr"]
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
    c3.metric(
        "Net burn (last 3 mo, actual)", money(actuals.net_burn_trailing_3mo, 0),
        "history — no lever changes this", delta_color="off",
    )
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
            charts.arr_trajectory(
                por_series, actuals.fy26_target, float(assumptions["fy27_arr_target"])),
            use_container_width=True,
        )
    with right:
        st.markdown("**Cash against the covenant floor**")
        st.plotly_chart(
            charts.cash_and_covenant(por_series, float(assumptions["min_cash_covenant"])),
            use_container_width=True,
        )

    st.markdown("**Monthly net burn**")
    st.plotly_chart(charts.burn_chart(por_series), use_container_width=True)

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
        f"{money(por_metrics['q4_2026_net_new_mrr'], 0)} modeled",
        delta_color="off",
    )
    q3.metric(
        "FY27 target", money(float(assumptions["fy27_arr_target"])),
        f"{money(por_metrics['fy27_exit_arr'])} modeled", delta_color="off",
    )

    st.divider()
    st.markdown("### How this is financed")
    st.caption(
        "The debt is real and already priced into every burn figure on this page. "
        "It is shown here because you are paying for it either way."
    )
    drawn = float(assumptions["debt_drawn"])
    undrawn = float(assumptions["debt_available"])
    rate = 11.0
    monthly_interest = drawn * (rate / 100) / 12
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Term loan drawn", money(drawn), f"{rate:.0f}%, interest-only through 2027",
              delta_color="off")
    f2.metric("Interest cost", f"{money(monthly_interest, 0)}/mo",
              f"{money(monthly_interest * 12, 0)}/yr — inside net burn", delta_color="off")
    f3.metric("Undrawn capacity", money(undrawn, 0), "the only uncommitted facility",
              delta_color="off")
    f4.metric("Minimum-cash covenant", money(float(assumptions["min_cash_covenant"])),
              "breach puts the loan at the lender's discretion", delta_color="off")
    st.markdown(esc_md(
        f"**No new equity is modelled.** This tool assumes no rescue round: the only "
        f"capital available is the {money(actuals.cash)} on hand and the {money(undrawn, 0)} "
        f"left on the line. That is what makes the {money(float(assumptions['min_cash_covenant']))} "
        f"floor binding rather than theoretical — there is nothing to call on if it breaks."
    ))

    st.divider()
    st.markdown(f"### The acquisition on the table — {target['target_name']}")
    acq_arr = float(target["arr_usd"])
    ask = float(target["asking_price_usd"])
    retention = float(target["gross_retention_pct"]) / 100
    retained_arr = acq_arr * retention
    tgt_opex_yr = float(target["monthly_opex_usd"]) * 12
    contribution = retained_arr - tgt_opex_yr
    redundant_saving = 3 * float(assumptions["loaded_cost_per_ae"]) * 12
    cross_sell_yr = 25_000 * 12
    mature = contribution + redundant_saving + cross_sell_yr
    payback = ask / mature

    st.markdown(
        f'<div class="flag-card" style="border-left-color:{charts.VIOLET};">'
        f'<div class="flag-sev" style="color:{charts.VIOLET};">◆ Deal terms as offered</div>'
        f'<div class="flag-body">'
        f'{esc_html(money(ask))} for {esc_html(money(acq_arr))} of trailing ARR — '
        f'<b>{ask / acq_arr:.2f}× ARR</b>. At {retention:.0%} gross retention only '
        f'{esc_html(money(retained_arr))} survives migration, so the effective price is '
        f'<b>{ask / retained_arr:.2f}× retained ARR</b>. The target carries '
        f'{esc_html(money(tgt_opex_yr))} of annual opex across {int(target["headcount"])} people, '
        f'{esc_html(money(float(target["integration_cost_usd"])))} of integration over six months, '
        f'and closes {str(target["expected_close"])[:7]}.'
        f'</div>'
        f'<div class="flag-body"><b>At the current rate:</b> retained revenue of '
        f'{esc_html(money(retained_arr))} against {esc_html(money(tgt_opex_yr))} of acquired opex '
        f'is <b>{esc_html(money(contribution))} a year of contribution before synergies</b>. '
        f'Eliminating three redundant roles and layering in cross-sell takes that to roughly '
        f'{esc_html(money(mature))} a year — a <b>~{payback:.0f}-year payback</b> on '
        f'{esc_html(money(ask))}.'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(esc_md(
        f"Cash on hand is {money(actuals.cash)}, but it is not all available. Holding the "
        f"{money(float(assumptions['min_cash_covenant']))} covenant floor leaves "
        f"**{money(actuals.cash - float(assumptions['min_cash_covenant']))} of genuinely "
        f"uncommitted cash** — and buying at the asking price commits "
        f"{money(ask)} of it. A rising cash balance in the months after a close is money that "
        f"is already spoken for."
    ))

    st.divider()
    st.markdown("### Plan integrity")
    st.caption("Deterministic rules, evaluated on the plan of record. No lever has been touched.")
    render_flags(por_flags, por_verdict)

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

    # A scenario that buys the revenue number by breaking the covenant is the
    # single most misreadable state in this tool: both facts are true, they sit
    # side by side, and the good one is the one people notice. State them as one
    # sentence, with the breach leading.
    arr_gain = metrics["fy26_exit_arr"] - por_metrics["fy26_exit_arr"]
    hits_target = metrics["fy26_variance"] >= 0
    if cov["breach"]:
        lede = (
            f"**This scenario buys the revenue number and breaks the balance sheet.** "
            if hits_target and arr_gain > 0 else
            f"**This scenario adds {money(arr_gain)} of FY26 ARR and breaks the balance sheet.** "
            if arr_gain > 0 else
            f"**This scenario breaks the balance sheet.** "
        )
        detail = (
            f"FY26 exits at {money(metrics['fy26_exit_arr'])} against the "
            f"{money(actuals.fy26_target)} target"
            + (f", {money(abs(metrics['fy26_variance']))} ahead" if hits_target
               else f", {money(abs(metrics['fy26_variance']))} short")
            + f". But cash falls below the {money(cov['min_cash_covenant'])} floor in "
            f"{cov['first_breach_month']} and stays there for {len(cov['breach_months'])} "
            f"{'month' if len(cov['breach_months']) == 1 else 'months'}, troughing at "
            f"{money(cov['trough_cash'])} in {cov['trough_month']}."
        )
        tail = (
            f" Cash goes negative in {metrics['cash_goes_negative_month']}."
            if metrics["cash_goes_negative_month"] else ""
        )
        closer = (
            " A breach puts the drawn balance at the lender's discretion, and no new equity "
            "is modelled — so there is nothing to call on."
        )
        st.error(esc_md(lede + detail + tail + closer))
    elif metrics["cash_goes_negative_month"]:
        st.error(
            f"**Cash goes negative in {metrics['cash_goes_negative_month']}** under this scenario."
        )

    st.divider()
    left, right = st.columns(2)
    baseline = por_series if scenario_changed else None
    if scenario_changed:
        st.caption(
            "Blue dotted is the plan of record — where today's plan leads if nobody acts. "
            "Orange is this scenario. The gap between them is what your levers bought."
        )
    with left:
        st.markdown("**ARR — actuals, plan of record, and this scenario**")
        st.plotly_chart(
            charts.arr_trajectory(
                series, actuals.fy26_target, float(assumptions["fy27_arr_target"]),
                baseline=baseline),
            use_container_width=True,
        )
    with right:
        st.markdown("**Cash against the covenant floor**")
        st.plotly_chart(
            charts.cash_and_covenant(
                series, float(assumptions["min_cash_covenant"]), baseline=baseline),
            use_container_width=True,
        )

    st.markdown("**Monthly net burn**")
    st.plotly_chart(charts.burn_chart(series, baseline=baseline), use_container_width=True)

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
