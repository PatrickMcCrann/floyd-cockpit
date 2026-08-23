"""The Plan Integrity Check.

Five deterministic rules. No LLM involvement: these fire (or don't) purely on the
computed model output, and the narrative layer is required to address each flag
that fires. Rules 1, 2 and 4 fire on the bundled data with no lever touched.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from data_loader import load_assumptions, load_target
from model import (
    Q4_2026,
    Scenario,
    midx,
    summarize_actuals,
)

SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2}


@dataclass
class Flag:
    rule: str
    severity: str          # critical | serious | warning
    headline: str
    contradiction: str     # the specific conflict, with numbers
    moves: list[str]       # 2-3 things that would close it

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt_money(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:,.2f}M"
    return f"${x / 1_000:,.0f}K"


def _fy26_at_list_price(scenario, metrics) -> float:
    """FY26 exit ARR for the same scenario with the price increase removed.

    Imported lazily to avoid a circular import: integrity is called from the
    forecast layer, not the other way round.
    """
    import dataclasses
    from model import run_forecast, scenario_metrics
    flat = dataclasses.replace(scenario, price_increase_pct=0.0)
    return scenario_metrics(flat, run_forecast(flat))["fy26_exit_arr"]


def _months_between(a: str, b: str) -> int:
    return midx(b) - midx(a)


def check_plan_integrity(scenario: Scenario, fc: pd.DataFrame, metrics: dict) -> list[Flag]:
    a = load_assumptions()
    t = load_target()
    s = summarize_actuals()
    flags: list[Flag] = []

    ramp = int(a["ae_ramp_months"])
    quota = float(scenario.ae_quota_net_new_mrr)
    required = float(a["q4_net_new_mrr_required"])

    # --- Rule 1: bookings capacity vs the Q4 target -------------------------
    capacity = metrics["q4_2026_net_new_mrr"]
    ae_contribution = metrics["q4_2026_ae_contribution_mrr"]
    if capacity < required:
        # The month AEs would have to start to be fully ramped by Oct 1.
        need_start = "2026-07"
        lag = _months_between(need_start, scenario.new_ae_start)
        if scenario.new_ae_hires > 0 and ae_contribution < 1000:
            timing = (
                f"The {scenario.new_ae_hires} planned AEs start {scenario.new_ae_start}; with a "
                f"{ramp}-month ramp they contribute {_fmt_money(ae_contribution)} of net-new MRR "
                f"in Q4 — effectively nothing. Full productivity by October required a "
                f"{need_start} start, {lag} months earlier than planned."
            )
        else:
            timing = (
                f"The {scenario.new_ae_hires} AEs starting {scenario.new_ae_start} contribute "
                f"{_fmt_money(ae_contribution)} in Q4 after the {ramp}-month ramp, against a "
                f"{_fmt_money(scenario.new_ae_hires * quota * 3)} fully-ramped quarter."
            )
        flags.append(
            Flag(
                rule="bookings_capacity_vs_target",
                severity="critical",
                headline="Q4 bookings capacity does not reach the FY27 ramp requirement",
                contradiction=(
                    f"The FY27 ramp requires {_fmt_money(required)} of net-new MRR in Q4 2026. "
                    f"The plan produces {_fmt_money(capacity)} — a shortfall of "
                    f"{_fmt_money(required - capacity)}. {timing}"
                ),
                moves=[
                    "Pull the AE start dates forward to the earliest feasible month and accept "
                    "that Q4 capacity is still partial — the ramp math cannot be recovered inside the quarter.",
                    f"Re-base the Q4 net-new MRR requirement to what capacity supports "
                    f"({_fmt_money(capacity)}) and re-phase the FY27 exit target accordingly.",
                    "Close the gap with price rather than headcount: a renewal price increase from "
                    "Oct 1 lands inside Q4 where a new AE cannot.",
                ],
            )
        )

    # --- Rule 2: at-risk renewals assumed to renew --------------------------
    at_risk = float(a["enterprise_renewals_at_risk_mrr"])
    if not scenario.at_risk_renewals_haircut:
        flags.append(
            Flag(
                rule="at_risk_renewals_assumed_renewed",
                severity="serious",
                headline="Forecast assumes at-risk enterprise renewals close",
                contradiction=(
                    f"{_fmt_money(at_risk)} of enterprise MRR across two logos is flagged at risk at "
                    f"the November 2026 renewal, and the active forecast carries all of it as renewing. "
                    f"That is {_fmt_money(at_risk * 12)} of ARR in the plan with no coverage. If it "
                    f"churns, FY26 exit ARR falls from {_fmt_money(metrics['fy26_exit_arr'])} to "
                    f"{_fmt_money(metrics['fy26_exit_arr'] - at_risk * 12)}."
                ),
                moves=[
                    "Run the scenario with the at-risk MRR haircut and re-read covenant headroom and runway.",
                    "Get a signed renewal or a written commitment on both logos before the board plan is set.",
                    f"Identify {_fmt_money(at_risk)} of offsetting pipeline that can close by November.",
                ],
            )
        )

    # --- Rule 3: covenant breach in any scenario month ----------------------
    cov = metrics["covenant"]
    if cov["breach"]:
        flags.append(
            Flag(
                rule="covenant_breach",
                severity="critical",
                headline="Cash falls below the minimum-cash covenant",
                contradiction=(
                    f"The venture term loan requires cash never to fall below "
                    f"{_fmt_money(cov['min_cash_covenant'])}. Under this scenario cash first breaches in "
                    f"{cov['first_breach_month']} and troughs at {_fmt_money(cov['trough_cash'])} in "
                    f"{cov['trough_month']} — {_fmt_money(abs(cov['headroom']))} below the floor, across "
                    f"{len(cov['breach_months'])} month(s)."
                ),
                moves=[
                    "Fund the cash draw differently — debt, seller note, or an earn-out — so the trough "
                    "stays above the floor.",
                    "Reduce the cash outlay or delay it past the trough month.",
                    "Negotiate a covenant waiver or reset with the lender before signing, not after.",
                ],
            )
        )
    elif cov["headroom"] < 1_000_000:
        flags.append(
            Flag(
                rule="covenant_headroom_thin",
                severity="warning",
                headline="Covenant headroom is thin",
                contradiction=(
                    f"Cash troughs at {_fmt_money(cov['trough_cash'])} in {cov['trough_month']}, leaving "
                    f"only {_fmt_money(cov['headroom'])} above the {_fmt_money(cov['min_cash_covenant'])} "
                    f"floor. One quarter of miss consumes it."
                ),
                moves=[
                    "Size the downside case explicitly and confirm the trough still clears the floor.",
                    "Pre-negotiate the undrawn line so it is available before the trough month.",
                ],
            )
        )

    # --- Rule 4: hiring ahead of capacity evidence --------------------------
    trailing = s.net_new_mrr_trailing_3mo
    planned_ae_mrr = scenario.new_ae_hires * quota
    if scenario.new_ae_hires > 0 and trailing > 0 and planned_ae_mrr > 2 * trailing:
        flags.append(
            Flag(
                rule="hiring_ahead_of_capacity_evidence",
                severity="serious",
                headline="Every new rep is expected to out-sell the whole company",
                contradiction=(
                    f"Each new AE is credited with {_fmt_money(quota)} of net-new MRR a month. At the "
                    f"current blended price of ${s.blended_arpu:,.0f} a customer, that is about "
                    f"{quota / s.blended_arpu:.0f} new logos every month, from one rep. The whole "
                    f"company is landing {s.new_logos_trailing_3mo:.0f} a month right now. So the plan "
                    f"asks {scenario.new_ae_hires} people to bring in about "
                    f"{scenario.new_ae_hires * quota / s.blended_arpu:.0f} logos a month between them — "
                    f"{scenario.new_ae_hires * quota / s.blended_arpu / max(s.new_logos_trailing_3mo, 1):.1f} "
                    f"times what everyone already here manages together. They cost "
                    f"{_fmt_money(scenario.new_ae_hires * float(a['loaded_cost_per_ae']))} a month from "
                    f"{scenario.new_ae_start} whether or not that happens."
                ),
                moves=[
                    f"Show pipeline coverage for {_fmt_money(planned_ae_mrr * 3)} of Q4 net-new before "
                    f"the reqs are opened.",
                    "Stage the hires — two now against demonstrated pipeline, two on a coverage trigger.",
                    "Validate the quota assumption against what the existing team actually produced this year.",
                ],
            )
        )

    # --- Rule 5: acquisition cash draw vs the minimum-cash guardrail --------
    if scenario.acquire_brightpath:
        draw = min(scenario.acquisition_debt_draw, float(a["debt_available"]))
        cash_out = scenario.acquisition_price - draw
        close_month = str(t["expected_close"])[:7]
        pre = fc[fc["month"] < close_month]
        pre_cash = float(pre.iloc[-1]["cash"]) if not pre.empty else s.cash
        post_cash = pre_cash - cash_out
        floor = float(a["min_cash_covenant"])
        if post_cash < floor:
            flags.append(
                Flag(
                    rule="acquisition_draw_vs_min_cash",
                    severity="critical",
                    headline="Acquisition cash outlay breaches the minimum-cash guardrail on close",
                    contradiction=(
                        f"Closing Brightpath at {_fmt_money(scenario.acquisition_price)} with "
                        f"{_fmt_money(draw)} drawn from the line takes {_fmt_money(cash_out)} out of cash "
                        f"in {close_month}. Cash goes from {_fmt_money(pre_cash)} to "
                        f"{_fmt_money(post_cash)} on the day of close — "
                        f"{_fmt_money(floor - post_cash)} below the {_fmt_money(floor)} covenant floor, "
                        f"before a single month of combined burn."
                    ),
                    moves=[
                        f"The undrawn line is only {_fmt_money(float(a['debt_available']))} — the structure "
                        f"has to change, not the draw. Seller paper or a staged earn-out is the only path "
                        f"that clears the floor.",
                        "Raise equity ahead of close to carry the purchase price.",
                        "Walk away from the acquisition and fund the organic path instead.",
                    ],
                )
            )
        elif post_cash - floor < 1_500_000:
            flags.append(
                Flag(
                    rule="acquisition_draw_vs_min_cash",
                    severity="serious",
                    headline="Acquisition leaves little room above the covenant floor",
                    contradiction=(
                        f"After a {_fmt_money(cash_out)} cash outlay at close, cash sits at "
                        f"{_fmt_money(post_cash)} — {_fmt_money(post_cash - floor)} above the "
                        f"{_fmt_money(floor)} floor, against combined monthly burn that includes "
                        f"{_fmt_money(float(t['monthly_opex_usd']))} of acquired opex."
                    ),
                    moves=[
                        "Model the combined burn against the floor month by month before signing.",
                        "Secure the redundancy savings on a defined date rather than assuming month 3.",
                    ],
                )
            )

    # --- Rule 6: modeled FY27 implausibly far above the board target --------
    # The same AE quota that barely covers Q4 produces roughly twice the FY27 target
    # when held as a run rate for a year. Both cannot be right; say so rather than
    # presenting the overshoot as a plan.
    fy27_target = float(a["fy27_arr_target"])
    fy27_modeled = metrics["fy27_exit_arr"]
    if scenario.new_ae_hires > 0 and fy27_modeled > fy27_target * 1.2:
        annual_ae_arr = scenario.new_ae_hires * quota * 12 * 12
        flags.append(
            Flag(
                rule="quota_assumption_unvalidated_over_fy27",
                severity="warning",
                headline="The forecast assumes the new reps keep growing at full speed forever",
                contradiction=(
                    f"The model keeps every AE producing {_fmt_money(quota)} of new MRR every month, "
                    f"for as long as the forecast runs. Nothing ever slows down. Compounded, that "
                    f"carries FY27 to {_fmt_money(fy27_modeled)} against a target of "
                    f"{_fmt_money(fy27_target)} — {_fmt_money(fy27_modeled - fy27_target)} above what "
                    f"the board is actually asking for. Real sales teams do not work that way: reps "
                    f"ramp, plateau, and some leave. Treat the back half of the FY27 line as an "
                    f"artefact of the assumption, not as money you have. The same quota is only just "
                    f"enough for the Q4 number, so it cannot be simultaneously too low for this year "
                    f"and far too high for next."
                ),
                moves=[
                    "Re-derive the quota from what the existing team actually produced in 2026 rather "
                    "than from the Q4 requirement worked backwards.",
                    "Model AE productivity as a declining curve after ramp rather than a flat "
                    "perpetual rate, and re-read FY27.",
                    "Treat FY27 exit ARR above the target as a modelling artefact, not headroom — do "
                    "not spend against it.",
                ],
            )
        )

    # --- Rule 8: a price increase with no churn response ---------------------
    if scenario.price_increase_pct > 0:
        uplift = metrics["fy26_exit_arr"] - _fy26_at_list_price(scenario, metrics)
        flags.append(
            Flag(
                rule="price_increase_no_churn_response",
                severity="serious" if scenario.price_increase_pct > 5 else "warning",
                headline="The price increase is modelled with nobody leaving over it",
                contradiction=(
                    f"A {scenario.price_increase_pct:.0f}% increase at renewal is carried straight "
                    f"to revenue: every customer renews, none negotiates, none leaves. Churn stays "
                    f"at {scenario.monthly_logo_churn_pct:.1f}% a month whatever the price does. "
                    f"That is the cheapest {_fmt_money(abs(uplift))} of ARR on this page, and the "
                    f"only lever here with no cost attached — which is the tell that a cost is "
                    f"missing rather than absent. Raising price on a base already losing "
                    f"{_fmt_money(float(a['enterprise_renewals_at_risk_mrr']))} of enterprise MRR at "
                    f"the November renewal is the part the model cannot see."
                ),
                moves=[
                    "Re-run with churn raised to whatever the CRO thinks a "
                    f"{scenario.price_increase_pct:.0f}% rise actually costs, and read the FY26 "
                    "number off that instead.",
                    "Segment it: hold price on the two at-risk enterprise logos and take the "
                    "increase only where retention is not already in question.",
                    "Do not present a price-led plan as equivalent to a capacity-led one — this "
                    "one carries a retention risk the model is not pricing.",
                ],
            )
        )

    flags.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return flags


def integrity_verdict(flags: list[Flag]) -> str:
    if any(f.severity == "critical" for f in flags):
        return "Plan integrity: at risk"
    if flags:
        return "Plan integrity: qualified"
    return "Plan integrity: clear"
