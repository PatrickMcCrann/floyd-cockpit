"""Deterministic Pandas forecast model for Copperline.

Every number the app displays or hands to the LLM is computed here. The narrative
layer never calculates; it only describes what this module returns.

Simplifications are listed in README.md under "Model simplifications". They are
labelled there rather than hidden here.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

from data_loader import load_actuals, load_assumptions, load_target

# --- Calendar helpers -------------------------------------------------------
# Months are "YYYY-MM" strings throughout. `midx` converts one to an integer
# ordinal so month arithmetic and comparisons are trivial.

LAST_ACTUAL = "2026-08"
FORECAST_START = "2026-09"
FY26_END = "2026-12"
FY27_END = "2027-12"


def midx(month: str) -> int:
    year, mon = month.split("-")
    return int(year) * 12 + int(mon)


def month_range(start: str, end: str) -> list[str]:
    out, cur = [], midx(start)
    stop = midx(end)
    while cur <= stop:
        year, mon = divmod(cur - 1, 12)
        out.append(f"{year:04d}-{mon + 1:02d}")
        cur += 1
    return out


FORECAST_MONTHS = month_range(FORECAST_START, FY27_END)
FY26_FORECAST_MONTHS = month_range(FORECAST_START, FY26_END)
Q4_2026 = ["2026-10", "2026-11", "2026-12"]

PRICE_EFFECTIVE = "2026-10"   # price increase hits at renewal from Oct 1

# Share of a renewing cohort that walks rather than accept the increase, per one
# percentage point of increase. At 0.5, a 10% rise loses 5% of each cohort as it
# comes up for renewal.
#
# This is an ASSUMPTION, not a measurement. Nothing in the supplied data records
# a past price change, so there is no elasticity to fit. It defaults non-zero
# because the alternative -- revenue that rises with nobody objecting -- is the
# one thing we know to be false. It does not touch the plan of record, which
# carries no increase. Argue with the number; do not leave it at zero by
# accident.
DEFAULT_PRICE_CHURN_SENSITIVITY = 0.5
MERIT_EFFECTIVE = "2027-01"   # company-wide +4% merit


# --- Scenario ---------------------------------------------------------------

@dataclass
class Scenario:
    """The levers on Screen 2. Defaults come from the bundled assumptions CSV."""

    new_logos_per_month: float
    monthly_logo_churn_pct: float
    net_revenue_retention_pct: float
    price_increase_pct: float
    new_ae_hires: int
    new_ae_start: str                    # "YYYY-MM"
    at_risk_renewals_haircut: bool       # False = base plan assumes they renew
    acquire_brightpath: bool
    acquisition_price: float
    acquisition_debt_draw: float         # drawn from the undrawn line, rest is cash
    debt_facility: float                 # undrawn capacity available to draw against
    ae_quota_net_new_mrr: float          # net-new MRR a fully ramped AE is assumed to add
    price_churn_sensitivity: float       # % of a renewing cohort lost per 1pt of increase

    @classmethod
    def from_defaults(cls) -> "Scenario":
        a = load_assumptions()
        t = load_target()
        return cls(
            new_logos_per_month=float(a["new_logos_per_month"]),
            monthly_logo_churn_pct=float(a["monthly_logo_churn_pct"]),
            net_revenue_retention_pct=float(a["net_revenue_retention_pct"]),
            price_increase_pct=float(a["price_increase_pct"]),
            new_ae_hires=int(a["new_ae_hires"]),
            new_ae_start=str(a["new_ae_start_date"])[:7],
            at_risk_renewals_haircut=False,
            acquire_brightpath=False,
            acquisition_price=float(t["asking_price_usd"]),
            acquisition_debt_draw=0.0,
            debt_facility=float(a["debt_available"]),
            ae_quota_net_new_mrr=float(a["ae_quota_net_new_mrr"]),
            price_churn_sensitivity=DEFAULT_PRICE_CHURN_SENSITIVITY,
        )

    def as_dict(self) -> dict:
        return asdict(self)


# --- Actuals summary --------------------------------------------------------

@dataclass
class ActualsSummary:
    last_month: str
    arr: float
    mrr: float
    customers: int
    core_customers: int
    enterprise_customers: int
    core_arpu: float
    enterprise_arpu: float
    headcount: int
    cash: float
    net_burn_last: float
    net_burn_trailing_3mo: float
    runway_months: float
    arr_growth_mom_pct: float
    net_new_mrr_trailing_3mo: float
    fy26_target: float
    gap_to_fy26_target: float
    # Sales performance in the unit a reader actually has intuition for. An AE
    # quota denominated in MRR means nothing until it is expressed as customers
    # per month against what the team is landing today.
    blended_arpu: float
    new_logos_trailing_3mo: float
    new_logos_ytd_mean: float
    churned_logos_trailing_3mo: float


def summarize_actuals() -> ActualsSummary:
    df = load_actuals()
    a = load_assumptions()
    last = df.iloc[-1]

    burn_3 = float(df["net_burn_usd"].tail(3).mean())
    cash = float(last["cash_balance_usd"])
    runway = cash / burn_3 if burn_3 > 0 else float("inf")

    mrr_now = float(last["mrr_usd"])
    mrr_3_ago = float(df["mrr_usd"].iloc[-4])
    net_new_3 = (mrr_now - mrr_3_ago) / 3.0

    mrr_prev = float(df["mrr_usd"].iloc[-2])

    customers_now = int(last["core_customers"] + last["enterprise_customers"])
    blended_arpu = mrr_now / customers_now if customers_now else 0.0

    return ActualsSummary(
        last_month=str(last["month"]),
        arr=float(last["arr_usd"]),
        mrr=mrr_now,
        customers=int(last["core_customers"] + last["enterprise_customers"]),
        core_customers=int(last["core_customers"]),
        enterprise_customers=int(last["enterprise_customers"]),
        core_arpu=float(last["core_arpu_usd"]),
        enterprise_arpu=float(last["enterprise_arpu_usd"]),
        headcount=int(last["headcount"]),
        cash=cash,
        net_burn_last=float(last["net_burn_usd"]),
        net_burn_trailing_3mo=burn_3,
        runway_months=runway,
        arr_growth_mom_pct=(mrr_now / mrr_prev - 1.0) * 100.0,
        net_new_mrr_trailing_3mo=net_new_3,
        fy26_target=float(a["fy26_arr_target"]),
        gap_to_fy26_target=float(a["fy26_arr_target"]) - float(last["arr_usd"]),
        blended_arpu=blended_arpu,
        new_logos_trailing_3mo=float(df["new_logos"].tail(3).mean()),
        new_logos_ytd_mean=float(df["new_logos"].mean()),
        churned_logos_trailing_3mo=float(df["churned_logos"].tail(3).mean()),
    )


# --- Opex trend -------------------------------------------------------------

SMOOTH_LINES = ["hosting_usd", "software_tools_usd", "office_ga_usd"]
LUMPY_LINES = ["marketing_programs_usd", "travel_events_usd", "prof_services_usd"]


def _opex_trend() -> tuple[dict, dict]:
    """Smooth lines extrapolate on their historical slope; lumpy lines carry at mean.

    Returns ({line: (base, per_month_delta)}, {line: flat_value}).
    """
    df = load_actuals()
    n = len(df)
    smooth = {}
    for col in SMOOTH_LINES:
        first, last = float(df[col].iloc[0]), float(df[col].iloc[-1])
        smooth[col] = (last, (last - first) / (n - 1))
    lumpy = {col: float(df[col].mean()) for col in LUMPY_LINES}
    return smooth, lumpy


def _ae_ramp_fraction(tenure_month: int, ramp_months: int) -> float:
    """Productivity fraction in the AE's `tenure_month`-th month (1 = start month).

    A 3-month ramp means months 1-3 are partial and month 4 is full: an AE starting
    July 1 is fully productive Oct 1. Linear in between.
    """
    if tenure_month <= 0:
        return 0.0
    return min(max(tenure_month - 1, 0) / float(ramp_months), 1.0)


# --- The forecast ------------------------------------------------------------

def run_forecast(scenario: Scenario) -> pd.DataFrame:
    """Roll the monthly model forward from the last actual month through Dec 2027."""
    a = load_assumptions()
    t = load_target()
    df_actual = load_actuals()
    last = df_actual.iloc[-1]

    churn = scenario.monthly_logo_churn_pct / 100.0
    expansion = (scenario.net_revenue_retention_pct / 100.0) ** (1.0 / 12.0) - 1.0
    ramp_months = int(a["ae_ramp_months"])
    quota = float(scenario.ae_quota_net_new_mrr)
    ae_cost = float(a["loaded_cost_per_ae"])
    merit = 1.0 + float(a["merit_increase_jan27_pct"]) / 100.0
    at_risk_mrr = float(a["enterprise_renewals_at_risk_mrr"])
    base_debt = float(a["debt_drawn"])

    # New-logo tier mix held at the Aug 2026 installed-base mix.
    core_share = float(last["core_customers"]) / float(
        last["core_customers"] + last["enterprise_customers"]
    )

    smooth, lumpy = _opex_trend()
    smooth_state = {col: smooth[col][0] for col in SMOOTH_LINES}

    # Opening state = Aug 2026 actuals.
    core_c = float(last["core_customers"])
    ent_c = float(last["enterprise_customers"])
    core_base_arpu = float(last["core_arpu_usd"])
    ent_base_arpu = float(last["enterprise_arpu_usd"])
    payroll_base = float(last["payroll_usd"])
    cash = float(last["cash_balance_usd"])
    ae_stock = 0.0
    crosssell_stock = 0.0
    acq_prev = 0.0
    debt = base_debt

    ae_start_i = midx(scenario.new_ae_start)
    price_i = midx(PRICE_EFFECTIVE)
    merit_i = midx(MERIT_EFFECTIVE)
    close_month = str(t["expected_close"])[:7]
    close_i = midx(close_month)
    at_risk_i = midx("2026-11")

    bp_mrr_at_close = float(t["arr_usd"]) / 12.0
    bp_retention = float(t["gross_retention_pct"]) / 100.0
    bp_opex = float(t["monthly_opex_usd"])
    bp_headcount = float(t["headcount"])
    bp_integration_total = float(t["integration_cost_usd"])

    def renewal_share(month_i: int) -> float:
        """Fraction of the base coming up for renewal in this month.

        Mirrors price_factor exactly: annual contracts, an even twelfth of the
        base repricing each month from the effective date. After twelve months
        the whole base has cycled through and there is nobody left to lose to
        this particular increase.
        """
        if scenario.price_increase_pct <= 0 or month_i < price_i:
            return 0.0
        if month_i - price_i >= 12:
            return 0.0
        return 1.0 / 12.0

    def price_factor(month_i: int) -> float:
        """1/12 of the base reprices each month from Oct 1 — renewal-only phase-in."""
        if scenario.price_increase_pct <= 0 or month_i < price_i:
            return 1.0
        elapsed = min(month_i - price_i + 1, 12)
        return 1.0 + (scenario.price_increase_pct / 100.0) * (elapsed / 12.0)

    rows = []
    for month in FORECAST_MONTHS:
        i = midx(month)
        pf_prev = price_factor(i - 1)
        pf_now = price_factor(i)

        core_arpu_prev_eff = core_base_arpu * pf_prev
        ent_arpu_prev_eff = ent_base_arpu * pf_prev

        # --- customers ---
        # Customers repricing this month who leave rather than pay. Applied to
        # the tier counts only: AE-sourced and acquired MRR are not facing this
        # renewal, so they are not exposed to it.
        refusal = (scenario.price_churn_sensitivity / 100.0) * scenario.price_increase_pct
        price_churn_rate = renewal_share(i) * refusal
        pchurn_core, pchurn_ent = core_c * price_churn_rate, ent_c * price_churn_rate

        churn_core, churn_ent = core_c * churn, ent_c * churn
        new_core = scenario.new_logos_per_month * core_share
        new_ent = scenario.new_logos_per_month * (1.0 - core_share)
        core_c_new = core_c - churn_core - pchurn_core + new_core
        ent_c_new = ent_c - churn_ent - pchurn_ent + new_ent

        # --- ARPU: NRR expansion on the base, then the renewal price factor ---
        core_base_new = core_base_arpu * (1.0 + expansion)
        ent_base_new = ent_base_arpu * (1.0 + expansion)

        # --- exact decomposition of the base-MRR change ---
        d_churn = -(churn_core * core_arpu_prev_eff + churn_ent * ent_arpu_prev_eff)
        d_price_churn = -(pchurn_core * core_arpu_prev_eff + pchurn_ent * ent_arpu_prev_eff)
        d_new = new_core * core_arpu_prev_eff + new_ent * ent_arpu_prev_eff
        d_expansion = (
            core_c_new * (core_base_new - core_base_arpu) * pf_prev
            + ent_c_new * (ent_base_new - ent_base_arpu) * pf_prev
        )
        d_price = (
            core_c_new * core_base_new * (pf_now - pf_prev)
            + ent_c_new * ent_base_new * (pf_now - pf_prev)
        )

        core_c, ent_c = core_c_new, ent_c_new
        core_base_arpu, ent_base_arpu = core_base_new, ent_base_new
        base_mrr = core_c * core_base_arpu * pf_now + ent_c * ent_base_arpu * pf_now

        # --- AE-sourced net-new MRR (a layer on top, churning like the base) ---
        tenure = i - ae_start_i + 1
        ae_added = (
            scenario.new_ae_hires * quota * _ae_ramp_fraction(tenure, ramp_months)
            if tenure >= 1
            else 0.0
        )
        ae_churn = ae_stock * churn
        ae_stock = ae_stock - ae_churn + ae_added
        d_ae = ae_added - ae_churn

        # --- at-risk enterprise renewals (Nov 2026) ---
        at_risk_loss = (
            at_risk_mrr if (scenario.at_risk_renewals_haircut and i >= at_risk_i) else 0.0
        )
        d_at_risk = -at_risk_mrr if (scenario.at_risk_renewals_haircut and i == at_risk_i) else 0.0

        # --- acquisition ---
        acq_mrr = 0.0
        acq_opex = 0.0
        integration = 0.0
        one_time = 0.0
        if scenario.acquire_brightpath and i >= close_i:
            since = i - close_i + 1                       # 1 in the close month
            # 85% gross retention read as an annual decay applied monthly.
            bp_mrr = bp_mrr_at_close * bp_retention ** ((since - 1) / 12.0)
            if since >= 7:
                crosssell_stock += 25000.0
            acq_mrr = bp_mrr + crosssell_stock
            # 3 of 14 roles redundant from month 3, costed pro-rata on target opex.
            acq_opex = bp_opex - (bp_opex * 3.0 / bp_headcount if since >= 3 else 0.0)
            integration = bp_integration_total / 6.0 if since <= 6 else 0.0
            if since == 1:
                draw = min(scenario.acquisition_debt_draw, scenario.debt_facility)
                one_time = scenario.acquisition_price - draw
                debt += draw
        d_acq = acq_mrr - acq_prev
        acq_prev = acq_mrr

        mrr = base_mrr + ae_stock - at_risk_loss + acq_mrr

        # --- costs ---
        merit_factor = merit if i >= merit_i else 1.0
        ae_headcount = scenario.new_ae_hires if i >= ae_start_i else 0
        payroll = (payroll_base + ae_headcount * ae_cost) * merit_factor

        for col in SMOOTH_LINES:
            smooth_state[col] = smooth_state[col] + smooth[col][1]
        other_opex = sum(smooth_state.values()) + sum(lumpy.values())
        interest = debt * 0.11 / 12.0

        total_opex = payroll + other_opex + interest + acq_opex + integration
        net_burn = total_opex - mrr
        cash = cash - net_burn - one_time

        rows.append(
            {
                "month": month,
                "core_customers": core_c,
                "enterprise_customers": ent_c,
                "customers": core_c + ent_c,
                "core_arpu": core_base_arpu * pf_now,
                "enterprise_arpu": ent_base_arpu * pf_now,
                "base_mrr": base_mrr,
                "ae_mrr": ae_stock,
                "at_risk_mrr": -at_risk_loss,
                "acquired_mrr": acq_mrr,
                "mrr": mrr,
                "arr": mrr * 12.0,
                "payroll": payroll,
                "other_opex": other_opex,
                "interest": interest,
                "acquisition_opex": acq_opex,
                "integration_cost": integration,
                "total_opex": total_opex,
                "net_burn": net_burn,
                "one_time_cash": one_time,
                "cash": cash,
                "debt": debt,
                "ae_headcount": ae_headcount,
                # bridge components (MRR deltas, exact by construction)
                "d_new_logos": d_new,
                "d_churn": d_churn,
                "d_expansion": d_expansion,
                "d_price": d_price,
                "d_price_churn": d_price_churn,
                "d_ae": d_ae,
                "d_at_risk": d_at_risk,
                "d_acquisition": d_acq,
            }
        )

    return pd.DataFrame(rows)


# --- Derived views ----------------------------------------------------------

def actuals_plus_forecast(fc: pd.DataFrame) -> pd.DataFrame:
    """One ARR/cash/burn series spanning Jan 2026 - Dec 2027, tagged actual vs forecast."""
    act = load_actuals()[["month", "arr_usd", "mrr_usd", "cash_balance_usd", "net_burn_usd"]].copy()
    act.columns = ["month", "arr", "mrr", "cash", "net_burn"]
    act["kind"] = "actual"
    f = fc[["month", "arr", "mrr", "cash", "net_burn"]].copy()
    f["kind"] = "forecast"
    return pd.concat([act, f], ignore_index=True)


def quarterly_fy27(fc: pd.DataFrame) -> pd.DataFrame:
    """FY27 by quarter: exit ARR, revenue, burn, ending cash."""
    f = fc[fc["month"].str.startswith("2027")].copy()
    f["quarter"] = "Q" + ((f["month"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    out = f.groupby("quarter").agg(
        exit_arr=("arr", "last"),
        revenue=("mrr", "sum"),
        total_opex=("total_opex", "sum"),
        net_burn=("net_burn", "sum"),
        ending_cash=("cash", "last"),
    ).reset_index()
    return out


def cash_negative_month(fc: pd.DataFrame) -> Optional[str]:
    below = fc[fc["cash"] < 0]
    return None if below.empty else str(below.iloc[0]["month"])


def covenant_status(fc: pd.DataFrame) -> dict:
    a = load_assumptions()
    floor = float(a["min_cash_covenant"])
    trough = fc.loc[fc["cash"].idxmin()]
    breaches = fc[fc["cash"] < floor]
    return {
        "min_cash_covenant": floor,
        "trough_cash": float(trough["cash"]),
        "trough_month": str(trough["month"]),
        "headroom": float(trough["cash"]) - floor,
        "breach": not breaches.empty,
        "first_breach_month": None if breaches.empty else str(breaches.iloc[0]["month"]),
        "breach_months": [str(m) for m in breaches["month"].tolist()],
    }


def runway_months(fc: pd.DataFrame, at_month: str = FY26_END) -> float:
    """Cash at `at_month` divided by the trailing 3-month average burn there."""
    idx = fc.index[fc["month"] == at_month]
    if len(idx) == 0:
        return float("nan")
    i = int(idx[0])
    cash = float(fc.loc[i, "cash"])
    burn = float(fc.loc[max(0, i - 2): i, "net_burn"].mean())
    if burn <= 0:
        return float("inf")
    return cash / burn


def revenue_bridge(fc: pd.DataFrame, through: str = FY26_END) -> list[dict]:
    """Aug-2026 ARR to `through` ARR, decomposed. Components sum exactly to the delta."""
    s = summarize_actuals()
    window = fc[fc["month"] <= through]
    comps = [
        ("New logos", "d_new_logos"),
        ("Churn", "d_churn"),
        ("Expansion (NRR)", "d_expansion"),
        ("Price increase", "d_price"),
        ("Lost to the increase", "d_price_churn"),
        ("New AE capacity", "d_ae"),
        ("At-risk renewals", "d_at_risk"),
        ("Brightpath", "d_acquisition"),
    ]
    out = [{"label": f"ARR {s.last_month}", "value": s.arr, "kind": "total"}]
    for label, col in comps:
        val = float(window[col].sum()) * 12.0
        if abs(val) > 1.0:
            out.append({"label": label, "value": val, "kind": "delta"})
    end_arr = float(window.iloc[-1]["arr"])
    out.append({"label": f"ARR {through}", "value": end_arr, "kind": "total"})
    return out


def scenario_metrics(scenario: Scenario, fc: pd.DataFrame) -> dict:
    """Everything the integrity check and the memo need, as plain JSON-able types."""
    a = load_assumptions()
    s = summarize_actuals()
    cov = covenant_status(fc)

    fy26_exit = float(fc[fc["month"] == FY26_END]["arr"].iloc[0])
    fy27_exit = float(fc[fc["month"] == FY27_END]["arr"].iloc[0])
    q4 = fc[fc["month"].isin(Q4_2026)]
    q4_net_new_mrr = float(
        q4["d_new_logos"].sum()
        + q4["d_churn"].sum()
        + q4["d_expansion"].sum()
        + q4["d_price"].sum()
        + q4["d_price_churn"].sum()
        + q4["d_ae"].sum()
        + q4["d_at_risk"].sum()
    )
    q4_ae_contribution = float(q4["d_ae"].sum())

    return {
        "fy26_exit_arr": fy26_exit,
        "fy26_target": float(a["fy26_arr_target"]),
        "fy26_variance": fy26_exit - float(a["fy26_arr_target"]),
        "fy27_exit_arr": fy27_exit,
        "fy27_target": float(a["fy27_arr_target"]),
        "fy27_variance": fy27_exit - float(a["fy27_arr_target"]),
        "q4_2026_net_new_mrr": q4_net_new_mrr,
        "q4_2026_net_new_mrr_required": float(a["q4_net_new_mrr_required"]),
        "q4_2026_ae_contribution_mrr": q4_ae_contribution,
        "dec_2026_cash": float(fc[fc["month"] == FY26_END]["cash"].iloc[0]),
        "dec_2027_cash": float(fc[fc["month"] == FY27_END]["cash"].iloc[0]),
        "avg_monthly_burn_q4_2026": float(q4["net_burn"].mean()),
        "runway_months_from_dec_2026": runway_months(fc, FY26_END),
        "cash_goes_negative_month": cash_negative_month(fc),
        "covenant": cov,
        "trailing_net_new_mrr_actual": s.net_new_mrr_trailing_3mo,
    }
