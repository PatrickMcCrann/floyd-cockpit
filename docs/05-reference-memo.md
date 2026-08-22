# Reference Output: CFO Decision Memo

*Unedited output from Screen 3 of the Growth Decision Cockpit. Fictional company,
synthetic data. Not financial, accounting, tax, legal or investment advice.*

**Generated:** 2026-08-22 · **Model:** `claude-opus-5` · **Scenario:** plan of record —
no lever touched (12 new logos/month, 1.8% monthly churn, 105% NRR, 0% price increase,
4 AE hires starting 2026-12, at-risk renewals assumed to renew, no acquisition)

## Why this file exists

This is the artifact behind the claim that the AI layer writes but never calculates.
Every figure below was computed by `model.py` and handed to the model as structured
JSON; the model received no raw data and no formulas. Each number here was checked
back against the model output and matches exactly — including the FY27 quarterly burn
discontinuity in the risk section, which the model flagged unprompted.

The four integrity flags it addresses fired deterministically on the bundled CSVs with
no lever moved. Regenerate this yourself from Screen 3, or reproduce it directly:

```python
from model import *
from integrity import check_plan_integrity
from narrative import build_payload, generate_memo

sc = Scenario.from_defaults()
fc = run_forecast(sc)
m = scenario_metrics(sc, fc)
flags = check_plan_integrity(sc, fc, m)
payload = build_payload(
    summarize_actuals(), sc, m, flags,
    quarterly_fy27(fc).to_dict(orient="records"),
    revenue_bridge(fc, FY26_END),
)
print(generate_memo(payload))
```

Output is non-deterministic — the prose will vary between runs, the figures will not.

---

# Copperline — CFO Decision Memo
**As of:** August 2026 · **Scenario:** base plan (no acquisition, no at-risk haircut, 4 AEs starting 2026-12)

## Executive readout

**[Fact]** Under the stated assumptions the model indicates FY26 exit ARR of **$12.56M against a $13.50M target — a shortfall of $935,659**, and the plan is carried by a Q4 2026 bookings step-up the actuals do not support. **[Fact]** Cash and covenant are not the near-term constraint: modeled trough cash is $5.31M in June 2027 against a $3.00M minimum, with $2.31M of headroom and no breach month. **[Fact]** Four integrity flags are open, one critical — this plan is not board-ready as written and should not be described as healthy.

## What changed / key drivers

Four drivers determine the outcome, in order of materiality:

1. **Q4 2026 bookings capacity vs. requirement [Fact].** The FY27 ramp requires $350K of net-new MRR in Q4 2026; the model produces **$33K** — a $317K shortfall. The 4 AEs start 2026-12 and contribute **$0** in Q4 under the stated 3-month ramp.
2. **Churn against new logos [Fact].** The Aug→Dec ARR bridge shows +$1,213,032 from new logos, **-$880,703 from churn**, and +$200,693 from expansion at 105% NRR. Churn absorbs roughly 73% of new-logo production; ARR grows $533K over five months.
3. **Unvalidated AE quota [Assumption].** The plan assumes 4 AEs at $22K net-new MRR each per month ($88K/mo fully ramped) against a trailing 3-month company-wide actual of **$15K/mo** — a 5.9x step-up on current run rate, at $66K/mo of loaded cost from 2026-12.
4. **At-risk enterprise renewals [Assumption].** $42K of enterprise MRR across two logos is flagged at risk at the November 2026 renewal and is carried in the forecast as renewing — **$504K of ARR with no coverage**.

## Scenario and risk assessment

| Dimension | Model output | Assessment |
|---|---|---|
| **Revenue** | FY26 exit ARR $12.56M vs $13.50M target (-$935,659) | **Off track.** FY27 modeled exit ARR of $24.73M vs $18.00M target (+$6.73M) is flagged as a modelling artefact, not headroom. |
| **Cash** | Dec 2026 cash $6.94M; Dec 2027 cash $6.85M; avg Q4 2026 net burn $441,164/mo | Stable under the stated assumptions; cash never goes negative in the modeled horizon. |
| **Runway** | 19.1 months at current burn; 15.7 months from Dec 2026 | Adequate, but this depends on the FY27 revenue ramp landing — Q3/Q4 2027 turn cash-generative (-$389,981 and -$1,149,672 net burn) only because ARR reaches $21.7M and $24.7M. Remove that ramp and the runway read changes. |
| **Covenant** | Minimum cash $3.00M; trough $5,310,269 in 2027-06; headroom $2,310,269; **no breach** | No breach modeled. Headroom has not been re-read under the at-risk-renewal haircut. |
| **Retention** | 1.8% monthly logo churn; 105% NRR; churn -$880,703 in the Aug–Dec bridge | The single largest drag on net ARR growth. Enterprise concentration is real: 55 enterprise customers at $6,550 ARPU, and two of them carry $42K MRR at November renewal. |
| **Execution** | 12 new logos/mo, 4 AE hires from 2026-12 | **Highest risk area.** The plan requires a 5.9x bookings step-up with no demonstrated pipeline coverage cited in the inputs. |

**[Limitation]** The payload contains no pipeline coverage data, no historical AE ramp curve, and no debt terms beyond the minimum-cash covenant. Q1 2027 shows revenue of $3.50M against opex of $4.72M and net burn of $1.22M — the largest single-quarter burn in the horizon — and the inputs do not explain the step-down to $409K in Q2. That discontinuity is unexplained by the supplied data and should be reconciled before the plan is set.

## Plan integrity

Four flags are open. All are addressed here; none is resolved.

**1. `bookings_capacity_vs_target` — CRITICAL.** Q4 bookings capacity does not reach the FY27 ramp requirement. Required $350K net-new MRR; plan produces $33K. The AE hires cannot recover this inside the quarter — full October productivity would have required a 2026-07 start, five months earlier than planned. **The FY27 ramp, as currently phased, does not have a feasible starting point.** Either the Q4 requirement is re-based to $33K and the FY27 exit target re-phased, or the gap is closed with a price action from Oct 1, which lands inside Q4 where an AE cannot. The active scenario carries a 0.0% price increase.

**2. `at_risk_renewals_assumed_renewed` — SERIOUS.** $504K of ARR is in the plan with no coverage. If it churns, FY26 exit ARR falls from $12.56M to **$12.06M**, widening the target variance. `at_risk_renewals_haircut` is set to `false`; covenant headroom and runway have **not** been read under the haircut. That re-read is a prerequisite to board approval.

**3. `hiring_ahead_of_capacity_evidence` — SERIOUS.** Trailing 3-month net-new MRR is $15K/mo company-wide — below a single AE's assumed $22K quota. The plan commits $66K/mo of loaded cost from 2026-12 against production the actuals do not evidence.

**4. `quota_assumption_unvalidated_over_fy27` — WARNING.** The same $22K quota that is only *just* sufficient for the Q4 requirement produces $12.67M of incremental ARR over a full year, carrying FY27 exit ARR to $24.73M against an $18.00M target. It cannot be correct in both places. **The $6.73M FY27 favorable variance should be treated as a modelling artefact and not spent against.**

## Recommended decision

**[Recommendation] Do not approve this plan as the board plan. Re-base the Q4 2026 net-new MRR requirement to the $33K the model shows capacity supports, re-phase the FY27 exit target off that base, and stage the AE hiring: open two reqs now against demonstrated pipeline coverage, hold two on a coverage trigger.**

Supporting actions, in sequence, before the board plan is set:

1. **Re-run the forecast with the at-risk renewal haircut on** and re-read trough cash, covenant headroom, and runway. Do not present a single-scenario cash picture that assumes two unsigned enterprise renewals close.
2. **Secure signed renewals or written commitments on both at-risk logos**, or identify $42K of offsetting pipeline closing by November.
3. **Re-derive the AE quota from what the existing team actually produced in 2026**, and model productivity as a declining post-ramp curve rather than a flat perpetual rate. Re-read FY27 on that basis.
4. **Evaluate an Oct 1 renewal price increase** as the only lever in the input set that can affect Q4 2026 — it is currently modeled at 0.0%. This memo does not recommend a specific percentage; that requires churn-elasticity data not present in the inputs.
5. **Present FY26 to the board at the modeled $12.56M**, with the $935,659 variance named, rather than at the target.

**Rationale:** cash and covenant give real time — 19.1 months of runway and $2.31M of trough headroom — and that time is better spent correcting the plan's arithmetic than defending a Q4 number that the ramp math shows cannot be delivered. Committing $66K/mo of AE cost against a 5.9x unevidenced step-up converts a revenue-timing problem into a burn problem.

## Leading indicators and triggers

| Indicator | Read by | Threshold | Trigger action |
|---|---|---|---|
| **Signed status, two at-risk enterprise logos ($42K MRR)** | 2026-10-31 | Not both signed or committed in writing | Re-forecast on the haircut basis as the primary case; FY26 exit ARR reads $12.06M |
| **Qualified Q4 pipeline coverage** | Before AE reqs open | Below 3x the re-based Q4 net-new target | Hold the second pair of AE hires; do not open reqs |
| **Monthly net-new MRR** | Monthly, from 2026-09 | Below the $14,883 trailing 3-month average for two consecutive months | Escalate to a demand-generation review; freeze remaining AE hiring |
| **Monthly logo churn** | Monthly | Above 1.8% for two consecutive months | Re-run FY27 — churn already offsets ~73% of new-logo ARR in the Aug–Dec bridge |
| **Net burn vs. Q4 2026 plan** | Monthly | Above $441,164/mo average | Re-read the Dec 2026 runway figure of 15.7 months |
| **Cash vs. covenant** | Monthly | Below $4.0M (i.e., headroom under $1.0M against the $3.0M minimum) | Escalate to the board and lender in advance; modeled trough is $5.31M in 2027-06 |
| **AE ramp actuals vs. $22K quota** | First full month post-ramp | Below 70% of assumed quota | Re-base FY27 exit ARR; the $24.73M figure does not survive a lower sustained rate |

**[Limitation]** Thresholds above are framed against the supplied model outputs. The 3x pipeline coverage ratio and the 70% quota-attainment threshold are conventional operating triggers, not model outputs — they are recommendations, not facts, and should be set against Copperline's own historical conversion data, which is not in this payload.