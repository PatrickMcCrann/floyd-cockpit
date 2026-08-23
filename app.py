"""Growth Decision Cockpit — Copperline (fictional).

Run:  streamlit run app.py

Three screens: Present Day, Decision Studio, Final Decision. All math is deterministic
and computed in model.py; the LLM writes narrative only, from computed metrics.
"""
from __future__ import annotations

import os

import streamlit as st

import charts
from data_loader import load_assumption_notes, load_assumptions, load_target
from integrity import check_plan_integrity, integrity_verdict
from model import (
    DEFAULT_PRICE_CHURN_SENSITIVITY,
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

st.set_page_config(page_title="Copperline — Growth Decision Cockpit", page_icon="◆", layout="wide")

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


def days_to(target_date: str) -> int:
    """Days from the close of the actuals to a fixed date in the scenario.

    Anchored to the last actual month-end, not to today's real clock: the story
    is set at 2026-08-31 and the deadlines have to move with the data, not with
    whenever someone happens to open the app.
    """
    from datetime import date
    y, m, d = (int(x) for x in target_date.split("-"))
    ly, lm = (int(x) for x in summarize_actuals().last_month.split("-"))
    last_day = date(ly + (lm // 12), (lm % 12) + 1, 1) - __import__("datetime").timedelta(days=1)
    return (date(y, m, d) - last_day).days


def months_label(m: float) -> str:
    if m == float("inf"):
        return "n/a — cash-flow positive"
    if m <= 0:
        return "Exhausted"
    return f"{m:.0f} months"


_ARPU = summarize_actuals().blended_arpu


def scenario_deltas(sc, base, tgt) -> list[str]:
    """Plain-language list of what this scenario changed, in the user's terms."""
    out = []
    if sc.new_logos_per_month != base.new_logos_per_month:
        out.append(f"new logos {base.new_logos_per_month:.0f} → {sc.new_logos_per_month:.0f} a month")
    if sc.monthly_logo_churn_pct != base.monthly_logo_churn_pct:
        out.append(f"churn {base.monthly_logo_churn_pct:.1f}% → {sc.monthly_logo_churn_pct:.1f}% a month")
    if sc.net_revenue_retention_pct != base.net_revenue_retention_pct:
        out.append(f"NRR {base.net_revenue_retention_pct:.0f}% → {sc.net_revenue_retention_pct:.0f}%")
    if sc.price_increase_pct != base.price_increase_pct:
        out.append(f"a {sc.price_increase_pct:.0f}% price increase at renewal")
    if sc.new_ae_hires != base.new_ae_hires:
        out.append(f"AE hires {base.new_ae_hires} → {sc.new_ae_hires}")
    if sc.new_ae_start != base.new_ae_start:
        out.append(f"AE start {base.new_ae_start} → {sc.new_ae_start}")
    if sc.at_risk_renewals_haircut != base.at_risk_renewals_haircut:
        out.append("the at-risk enterprise renewals taken as lost")
    if sc.acquire_brightpath != base.acquire_brightpath:
        out.append(f"acquiring {tgt['target_name']} at {money(sc.acquisition_price)}")
    elif sc.acquire_brightpath and sc.acquisition_price != base.acquisition_price:
        out.append(f"a {money(sc.acquisition_price)} purchase price")
    if sc.price_churn_sensitivity != base.price_churn_sensitivity and sc.price_increase_pct > 0:
        out.append(
            f"price sensitivity {base.price_churn_sensitivity:.1f} → "
            f"{sc.price_churn_sensitivity:.1f}% lost per point")
    if abs(sc.ae_quota_net_new_mrr - base.ae_quota_net_new_mrr) > 1:
        out.append(
            f"AE productivity {base.ae_quota_net_new_mrr / _ARPU:.1f} → "
            f"{sc.ae_quota_net_new_mrr / _ARPU:.1f} logos per rep a month")
    if sc.debt_facility != base.debt_facility:
        out.append(f"the facility raised to {money(sc.debt_facility, 0)}")
    if sc.acquisition_debt_draw != base.acquisition_debt_draw:
        out.append(f"{money(sc.acquisition_debt_draw, 0)} drawn from the facility")
    return out


def plain_readout(sc, base, m, pm, fcst, por_fcst, tgt) -> str:
    """A deterministic English summary of the active scenario.

    Sits between moving a lever and paying for a memo: the memo costs money and
    takes seconds, so nobody generates one per toggle. Written by arithmetic,
    not by the model.

    Returns HTML, not Markdown: it is rendered inside an unsafe_allow_html card,
    where `**bold**` would come out as literal asterisks.
    """
    cov = m["covenant"]
    changes = scenario_deltas(sc, base, tgt)
    if changes:
        joined = changes[0] if len(changes) == 1 else (
            ", ".join(changes[:-1]) + " and " + changes[-1])
        opener = f"<b>You changed {joined}.</b>"
    else:
        opener = "<b>This is the present day plan — nothing has been changed yet.</b>"

    arr_delta = m["fy26_exit_arr"] - pm["fy26_exit_arr"]
    moved = abs(arr_delta) >= 5_000
    if moved:
        vs_plan = (f", {money(abs(arr_delta))} "
                   f"{'more' if arr_delta > 0 else 'less'} than the present day plan")
    elif changes:
        vs_plan = ", unchanged from the present day plan"
    else:
        vs_plan = ""
    vs_target = (f"{money(abs(m['fy26_variance']))} "
                 f"{'ahead of' if m['fy26_variance'] >= 0 else 'short of'} the board target")
    # "and" only reads correctly when a clause precedes it.
    rev = (f"FY26 exits at {money(m['fy26_exit_arr'])}{vs_plan}"
           + (f", and {vs_target}. " if vs_plan else f", {vs_target}. "))

    trough = f"{money(cov['trough_cash'])} in {cov['trough_month']}"
    if cov["breach"]:
        cash = (f"Cash troughs at {trough}, below the "
                f"{money(cov['min_cash_covenant'])} floor from {cov['first_breach_month']}. ")
    else:
        cash = (f"Cash troughs at {trough}, holding "
                f"{money(cov['headroom'])} above the floor. ")

    interest_total = float(fcst["interest"].sum())
    interest_base = float(por_fcst["interest"].sum())
    extra = interest_total - interest_base
    debt_note = (
        f"Interest runs {money(interest_total)} across the horizon"
        + (f", {money(extra)} more than the present day plan. " if extra >= 500 else ". ")
    )

    if cov["breach"]:
        watch = ("<b>The binding constraint is the covenant, not growth</b> — this path defaults "
                 "the loan before the revenue arrives.")
    elif m["runway_months_from_dec_2026"] < 12:
        watch = (f"<b>The binding constraint is runway</b> — "
                 f"{months_label(m['runway_months_from_dec_2026'])} from Dec 2026.")
    elif m["fy26_variance"] < 0:
        watch = (f"<b>The binding constraint is the FY26 gap</b> — "
                 f"{money(abs(m['fy26_variance']))} short, or "
                 f"{money(abs(m['fy26_variance']) / 12 / 4, 0)} of net-new MRR a month "
                 f"across the four months that remain.")
    elif m["q4_2026_net_new_mrr"] < m["q4_2026_net_new_mrr_required"]:
        watch = (f"<b>The binding constraint is Q4 bookings</b> — "
                 f"{money(m['q4_2026_net_new_mrr'], 0)} against the "
                 f"{money(m['q4_2026_net_new_mrr_required'], 0)} the FY27 ramp requires.")
    else:
        watch = "<b>No rule fires against this scenario.</b> It clears revenue, cash and covenant."

    return opener + " " + rev + cash + debt_note + watch


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

st.sidebar.markdown("### ◆ Growth Decision Cockpit")
st.sidebar.caption("Copperline · a fictional company, synthetic data")

screen = st.sidebar.radio(
    "Screen",
    ["1 · Present Day", "2 · Decision Studio", "3 · Final Decision"],
    label_visibility="collapsed",
)

show_levers = screen.startswith("2")

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
    "facility_k": int(float(assumptions["debt_available"]) / 1e3),
    # Quota is stored in logos/rep/month because that is the unit anyone can
    # argue with. The plan's $22K converts to about 10.5, against 11 for the
    # entire company -- an absurdity that is invisible while it stays in MRR.
    "ae_logos": round(float(assumptions["ae_quota_net_new_mrr"])
                      / summarize_actuals().blended_arpu, 1),
    "price_sens": DEFAULT_PRICE_CHURN_SENSITIVITY,
}


def lv(name):
    """Current value of a lever, whether or not its widget is on screen."""
    return st.session_state.get(f"val_{name}", LEVER_DEFAULTS[name])


def wkey(name: str) -> str:
    """Widget key, namespaced by a reset counter.

    Reset works by bumping the counter, which gives every widget a key it has
    never seen and therefore its default value. Deleting session_state alone
    does not do it: Streamlit restores a widget from its own internal store when
    the key is unchanged, so the toggles kept their old positions while the
    numbers underneath them reset -- the worst possible failure, because the
    screen then disagrees with itself.
    """
    return f"lever_{name}_{st.session_state.get('reset_nonce', 0)}"


def keep(name, value):
    st.session_state[f"val_{name}"] = value
    return value


if show_levers:
    st.sidebar.divider()
    st.sidebar.markdown("**Levers**")

    if st.sidebar.button("Reset to the present day plan", width="stretch"):
        for k in [k for k in st.session_state if k.startswith(("lever_", "val_"))]:
            del st.session_state[k]
        st.session_state["reset_nonce"] = st.session_state.get("reset_nonce", 0) + 1
        st.session_state.pop("memo", None)
        st.session_state.pop("memo_fingerprint", None)
        st.rerun()

    st.sidebar.markdown("_Current trajectory_")
    keep("logos", st.sidebar.slider(
        "New logos / month", 0, 40, lv("logos"), key=wkey("logos")))
    keep("churn", st.sidebar.slider(
        "Monthly logo churn (%)", 0.0, 6.0, lv("churn"), 0.1, key=wkey("churn")))
    keep("nrr", st.sidebar.slider(
        "Net revenue retention (%)", 90, 140, lv("nrr"), key=wkey("nrr")))
    keep("price", st.sidebar.slider(
        "Price increase at renewal, from Oct 1 (%)", 0, 25, lv("price"), key=wkey("price")))

    keep("price_sens", st.sidebar.slider(
        "Customers lost per 1% of increase (%)", 0.0, 2.0, float(lv("price_sens")), 0.1,
        key=wkey("price_sens"), disabled=lv("price") == 0,
        help="Of the customers repricing in a given month, the share that leaves rather "
             "than pay, for each point of increase. An assumption — nothing in our data "
             "records a past price change — but zero is the one value we know is wrong.",
    ))
    if lv("price") > 0:
        _ref = lv("price_sens") / 100.0 * lv("price")
        st.sidebar.caption(esc_md(
            f"A {lv('price'):.0f}% rise loses {_ref:.1%} of each renewing cohort — about "
            f"{_ref * summarize_actuals().customers:.0f} customers over the twelve months "
            f"it takes the base to cycle through."
            + ("  \n**At zero, revenue rises and nobody objects.**" if lv("price_sens") == 0 else "")
        ))

    st.sidebar.markdown("_Sales capacity_")
    keep("aes", st.sidebar.slider("New AE hires", 0, 12, lv("aes"), key=wkey("aes")))
    start_options = month_range("2026-09", "2027-06")
    keep("ae_start", st.sidebar.selectbox(
        "AE start month", start_options,
        index=start_options.index(lv("ae_start")), key=wkey("ae_start")))
    st.sidebar.caption(esc_md(
        f"{int(assumptions['ae_ramp_months'])}-month ramp to "
        f"{money(float(assumptions['ae_quota_net_new_mrr']), 0)}/mo quota. A rep books "
        f"nothing in month 1, so a start date late in the year contributes nothing to FY26."
    ))

    _arpu = summarize_actuals().blended_arpu
    _company_logos = summarize_actuals().new_logos_trailing_3mo
    keep("ae_logos", st.sidebar.slider(
        "New logos each AE lands / month", 0.0, 12.0, float(lv("ae_logos")), 0.5,
        key=wkey("ae_logos"),
        help="The board plan credits each rep with about 10.5 logos a month. The whole "
             "company lands 11. Drag this down to whatever you actually believe a new "
             "rep will close, and watch the plan change shape.",
    ))
    _q = lv("ae_logos") * _arpu
    _plan_logos = LEVER_DEFAULTS["ae_logos"]
    st.sidebar.caption(esc_md(
        f"= {money(_q, 0)}/mo of quota per rep. "
        + (f"Board plan is {_plan_logos:.1f}. "
           if abs(lv("ae_logos") - _plan_logos) > 0.05 else "This is the board plan. ")
        + f"{lv('aes')} reps at this rate add "
        f"{lv('aes') * lv('ae_logos'):.0f} logos/mo against "
        f"{_company_logos:.0f} company-wide today."
    ))

    st.sidebar.markdown("_Retention_")
    keep("haircut", st.sidebar.checkbox(
        esc_md(
            f"Haircut {money(float(assumptions['enterprise_renewals_at_risk_mrr']), 0)} at-risk "
            f"enterprise MRR (Nov)"
        ),
        value=lv("haircut"), key=wkey("haircut")))

    st.sidebar.markdown("_Acquisition_")
    keep("acquire", st.sidebar.checkbox(
        f"Acquire {target['target_name']}", value=lv("acquire"), key=wkey("acquire")))
    keep("acq_price_m", st.sidebar.slider(
        "Purchase price ($M)", 4.0, 10.0, lv("acq_price_m"), 0.1,
        key=wkey("acq_price"), disabled=not lv("acquire")))
    st.sidebar.markdown("_Financing_")
    keep("facility_k", st.sidebar.slider(
        "Undrawn facility available ($K)", 0, 6000, lv("facility_k"), 250,
        key=wkey("facility"),
        help="The plan of record has $500K left on the venture line. That is thin against "
             "$12M of ARR, and it makes borrow-versus-don't a choice you cannot actually "
             "explore. Raise it to test what a larger facility would buy — the default is "
             "the figure in the supplied data.",
    ))
    draw_cap = max(int(lv("facility_k")), 0)
    keep("acq_draw_k", st.sidebar.slider(
        "Funded from the facility ($K)", 0, max(draw_cap, 1),
        min(lv("acq_draw_k"), draw_cap), 50,
        key=wkey("acq_draw"), disabled=not lv("acquire") or draw_cap == 0))
    if lv("acquire"):
        st.sidebar.caption(esc_md(
            f"Balance out of cash: {money(lv('acq_price_m') * 1e6 - lv('acq_draw_k') * 1e3)}. "
            f"Closes {str(target['expected_close'])[:7]}."
        ))
    if lv("facility_k") != LEVER_DEFAULTS["facility_k"]:
        st.sidebar.caption(esc_md(
            f"Facility raised from {money(float(assumptions['debt_available']), 0)} to "
            f"{money(lv('facility_k') * 1e3, 0)} — a deviation from the supplied data."
        ))
elif screen.startswith("1"):
    st.sidebar.divider()
    st.sidebar.caption(
        "This screen is the fixed baseline — the present day plan, before any decision. "
        "The levers live in the Decision Studio."
    )
else:
    st.sidebar.divider()
    st.sidebar.caption(
        "The memo is written for whatever the Decision Studio is set to. To change the "
        "scenario, go back to screen 2 — the settings in force are shown on the page."
    )

new_logos, churn, nrr, price = lv("logos"), lv("churn"), lv("nrr"), lv("price")
ae_hires, ae_start = lv("aes"), lv("ae_start")
haircut, acquire = lv("haircut"), lv("acquire")
acq_price = lv("acq_price_m") * 1e6
acq_draw = lv("acq_draw_k") * 1e3
facility = lv("facility_k") * 1e3
# Snap to the filed figure when the slider is untouched. The UI shows logos to
# one decimal, so converting back through ARPU lands ~$22 off the CSV quota —
# enough to make scenario != defaults forever and leave the "changed" overlay
# permanently on, which is worse than the rounding it came from.
if abs(lv("ae_logos") - LEVER_DEFAULTS["ae_logos"]) < 1e-9:
    ae_quota = float(assumptions["ae_quota_net_new_mrr"])
else:
    ae_quota = lv("ae_logos") * summarize_actuals().blended_arpu

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
    debt_facility=float(facility),
    ae_quota_net_new_mrr=float(ae_quota),
    price_churn_sensitivity=float(lv("price_sens")),
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
    st.title("Present Day")
    st.caption(
        f"Copperline · actuals through {actuals.last_month} · "
        f"{actuals.customers} customers · {actuals.headcount} heads"
    )

    st.markdown(esc_md(
        "I built this so we can settle the growth question together rather than in a "
        "spreadsheet I email round afterwards. Eight months of FY26 actuals are on the books; September "
        "through December remain, plus the FY27 plan to set. The board wants "
        f"{money(actuals.fy26_target)} exit ARR this year and "
        f"{money(float(assumptions['fy27_arr_target']))} next — roughly 49% growth — and the "
        "CEO wants to accelerate to get there, by hiring account executives, by acquiring "
        f"{target['target_name']}, or both.\n\n"
        "**Read this page top to bottom — it is where we actually are, and nothing on it "
        "moves.** At the bottom you will find how to use the other two screens to test a "
        "way out and turn it into a memo for the board.\n\n"
        f"**The clock is the constraint.** Q4 opens {days_to('2026-10-01')} days from the close of "
        f"these books, and a renewal price increase only bites from Oct 1. "
        f"{target['target_name']} closes {days_to('2026-11-01')} days out, on "
        f"{str(target['expected_close'])[:10]} — after that the option is gone. Account "
        f"executives hired today do not carry full quota until "
        f"{int(assumptions['ae_ramp_months'])} months after they start, which is why the "
        f"start date matters more than the headcount."
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
    st.markdown("### What sales actually produces today")
    st.caption(
        "The plan is written in MRR. This is the same thing in customers, which is "
        "the unit the number has to be argued in."
    )
    quota_mrr = float(assumptions["ae_quota_net_new_mrr"])
    logos_per_ae = quota_mrr / actuals.blended_arpu
    planned_aes = int(assumptions["new_ae_hires"])
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("New logos landed / month", f"{actuals.new_logos_trailing_3mo:.0f}",
              f"{actuals.new_logos_ytd_mean:.1f} average across 2026", delta_color="off")
    s2.metric("Customers lost / month", f"{actuals.churned_logos_trailing_3mo:.0f}",
              f"net +{actuals.new_logos_trailing_3mo - actuals.churned_logos_trailing_3mo:.0f} a month",
              delta_color="off")
    s3.metric("Blended price / customer", f"${actuals.blended_arpu:,.0f}",
              "MRR ÷ customers", delta_color="off")
    s4.metric("Each new AE is expected to land", f"{logos_per_ae:.0f} logos/mo",
              f"{money(quota_mrr, 0)} of quota", delta_color="off")
    st.markdown(esc_md(
        f"The lever labelled *New logos / month* is bookings. It sits at "
        f"{actuals.new_logos_ytd_mean:.0f} because that is what Copperline actually landed, "
        f"on average, every month this year — it is not a target. Each new AE is credited "
        f"with {logos_per_ae:.0f} more a month on top, so {planned_aes} of them are assumed to "
        f"bring in about {planned_aes * logos_per_ae:.0f} a month between them, roughly "
        f"{planned_aes * logos_per_ae / max(actuals.new_logos_trailing_3mo, 1):.1f}× what the "
        f"whole company lands today. That is the assumption to argue with first."
    ))

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
    st.markdown("### What worries me about the present day plan")
    st.caption(
        "Before any of us has changed anything. These run on maths, not opinion — each one "
        "is a place where two things we have already committed to cannot both be true."
    )
    st.markdown(esc_md(
        "Read them in order. The first decides our year: **we do not have the "
        "people to book what Q4 needs, and hiring now cannot fix it in time** — a rep hired "
        "today is not at full quota until the quarter is over. The second is revenue we are "
        "already counting that may not arrive — the Decision Studio has a toggle to take "
        "that haircut and see what it costs us. The last two are about the sales assumption itself, "
        "and they pull in opposite directions: the quota is too small to rescue Q4 and too "
        "large to believe for a full year. At most one of those can be right."
    ))
    render_flags(por_flags, por_verdict)

    st.divider()
    st.markdown("### How to use this tool")
    st.markdown(esc_md(
        f"**1 · Present Day** — this page. Where we are, fixed.\n\n"
        f"**2 · Decision Studio** is where you change it. Move new logos, churn, retention "
        f"and price for the trajectory; move AE headcount and start date for capacity; "
        f"toggle the {target['target_name']} acquisition and how much of it is borrowed. "
        f"Everything recomputes, and the present day plan stays on every chart as a dotted "
        f"blue line so you can see what your choice actually bought.\n\n"
        f"**3 · Final Decision** — turn the scenario you settled on into a memo for the "
        f"board. Generate one per scenario if you want options side by side.\n\n"
        f"We have to decide before {str(target['expected_close'])[:10]} — "
        f"{days_to('2026-11-01')} days — or the acquisition question answers itself."
    ))

    with st.expander("Actuals detail — Jan–Aug 2026"):
        from data_loader import load_actuals
        st.dataframe(load_actuals(), width="stretch", hide_index=True)

# ============================================================================
# SCREEN 2 — Decision studio
# ============================================================================
elif screen.startswith("2"):
    st.title("Decision Studio")
    st.caption(
        "Move a lever in the sidebar. Revenue, cash, runway, covenant headroom and the "
        "integrity check all recompute, and the present day plan stays on every chart "
        "so you can see what changed."
    )
    if scenario_changed:
        st.markdown(
            '<div class="caption-note">Scenario differs from the present day plan.</div>',
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

    st.markdown(
        f'<div class="flag-card" style="border-left-color:{charts.VIOLET};">'
        f'<div class="flag-sev" style="color:{charts.VIOLET};">◆ What this scenario does</div>'
        f'<div class="flag-body">'
        f'{esc_html(plain_readout(scenario, defaults, metrics, por_metrics, fc, por_fc, target))}'
        f'</div></div>',
        unsafe_allow_html=True,
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
            "Blue dotted is the present day plan — where today's plan leads if nobody acts. "
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
    st.markdown("### Where your changes leave plan integrity")
    st.caption(
        "Re-run against the scenario above, not the present day plan. A flag that "
        "clears here is one your choice actually fixed."
    )
    render_flags(flags, verdict)

# ============================================================================
# SCREEN 3 — The memo
# ============================================================================
else:
    st.title("Final Decision")
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

    # Read-only. The levers deliberately are not on this screen: this page is for
    # publishing a decision, not still making one.
    st.divider()
    st.markdown("### The scenario this memo describes")
    changed = scenario_deltas(scenario, defaults, target)
    st.caption(
        "Changed from the present day plan: " + ("; ".join(changed) if changed else
        "nothing — this is the present day plan as filed.")
        + ". To change it, go back to the Decision Studio."
    )
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("New logos / month", f"{scenario.new_logos_per_month:.0f}",
              f"present day plan {defaults.new_logos_per_month:.0f}", delta_color="off")
    r2.metric("Monthly churn", f"{scenario.monthly_logo_churn_pct:.1f}%",
              f"NRR {scenario.net_revenue_retention_pct:.0f}%", delta_color="off")
    r3.metric("AE hires", f"{scenario.new_ae_hires}",
              f"from {scenario.new_ae_start}", delta_color="off")
    r4.metric(f"Acquire {target['target_name'].split()[0]}",
              "Yes" if scenario.acquire_brightpath else "No",
              money(scenario.acquisition_price) if scenario.acquire_brightpath
              else "price increase " + f"{scenario.price_increase_pct:.0f}%",
              delta_color="off")

    st.divider()
    st.markdown("### The picture behind the memo")
    st.caption(
        "The same charts the Decision Studio shows, so the memo can be read against "
        "them rather than on trust. Dotted blue is the present day plan."
    )
    memo_baseline = por_series if scenario_changed else None
    mc1, mc2 = st.columns(2)
    with mc1:
        st.plotly_chart(
            charts.arr_trajectory(
                series, actuals.fy26_target, float(assumptions["fy27_arr_target"]),
                baseline=memo_baseline),
            use_container_width=True,
        )
    with mc2:
        st.plotly_chart(
            charts.cash_and_covenant(
                series, float(assumptions["min_cash_covenant"]), baseline=memo_baseline),
            use_container_width=True,
        )

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
        with st.spinner("Writing the memo…"):
            try:
                st.session_state["memo"] = generate_memo(payload, effective_key or None)
                st.session_state["memo_fingerprint"] = fingerprint
            except NarrativeError as exc:
                st.error(str(exc))

    memo = st.session_state.get("memo")
    if memo:
        with st.container(border=True):
            # Escape on display only. Streamlit reads $...$ as LaTeX, and a CFO memo
            # is almost entirely dollar figures, so an unescaped memo renders
            # "$12.56M against a $13.50M target" as italic maths. The download keeps
            # the raw text so the .md file has plain dollar signs.
            st.markdown(esc_md(memo))
        st.download_button(
            "Download memo (Markdown)", memo,
            file_name=f"copperline-cfo-memo-{actuals.last_month}.md",
            mime="text/markdown",
        )
    else:
        st.info(
            "Press **Generate memo**. It is written for the scenario shown above; change "
            "that in the Decision Studio and generate again to compare options."
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
