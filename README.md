# Floyd — Growth Decision Cockpit

A CFO decision tool for **Copperline**, a fictional Series B B2B SaaS company. It is
August 31, 2026. Eight months of actuals are on the books; September through December
remain, plus the FY27 plan to set. The CEO wants to accelerate — hire 4 AEs, or acquire
a smaller competitor, or both. This tells the CFO which path survives contact with cash,
covenant, and capacity.

**All data is synthetic. Fictional company. Not financial, accounting, tax, legal or
investment advice.**

## Try it

**Live, no setup, no API key:** https://thesuiteforecasting.streamlit.app

## Run it

One line, clone to running:

```bash
git clone https://github.com/PatrickMcCrann/floyd-cockpit && cd floyd-cockpit && pip install -r requirements.txt && streamlit run app.py
```

**No API key is needed to run it.** Screens 1 and 2 — the actuals, the forecast, the
scenario levers, and the Plan Integrity Check — are fully functional without one,
because every number in this tool is computed by Pandas, not by a model.

Screen 3 writes the CFO memo with Claude, so it needs a key. Add one either way:

```bash
cp .env.example .env && $EDITOR .env      # ANTHROPIC_API_KEY=sk-ant-...
```

or paste a key straight into the sidebar field at runtime. To see the memo without a
key at all, `docs/05-reference-memo.md` is a full unedited Screen 3 output, with every
figure traced back to the model.

That is the whole setup. The three CSVs in `/data` are bundled — there is no uploader
and no integration. Screens 1 and 2 work with no key at all.

The key is read from, in order: the sidebar field, then `ANTHROPIC_API_KEY` in the
environment, then a `.env` file next to `app.py`. `.env` is gitignored, and a project
-local file is preferred over `export ANTHROPIC_API_KEY=...`, which would also point
every other tool on your machine at the same key. Loading it needs no extra dependency
— there is a small parser in `narrative.py`.

To regenerate the synthetic data: `python generate_data.py`.

## How it's built

```
model.py       deterministic Pandas forecast — every number the app shows
integrity.py   the Plan Integrity Check — six deterministic rules
charts.py      Plotly figures, one shared palette and layout
narrative.py   the LLM call: computed metrics in as JSON, prose out
app.py         Streamlit UI, three screens
data_loader.py CSV loading
```

**The AI never calculates.** `model.py` computes; `narrative.py` hands Claude
(`claude-opus-5`) a structured JSON payload of *results* and the system prompt from
`SYSTEM_PROMPT.md`, and the model writes the memo. It never sees raw data or formulas,
so it has nothing to do arithmetic with. Screen 3 shows the exact payload it receives,
verbatim, in an expander — the numbers in the memo are checkable against it line by line.

## The three screens

**1 · Where we stand.** Actuals through August: ARR trajectory, burn, cash, runway, and
the gap to the $13.5M FY26 target, with a single status line saying on plan or off, and
by how much. The integrity check runs here too, on the untouched plan of record.

**2 · Decision studio.** The levers — new logos/month, monthly churn, NRR, price increase
at renewal, AE count and start date, at-risk renewal treatment, and an acquire-Brightpath
toggle with price and cash-vs-debt funding. Everything recomputes on change: monthly
forecast Sep–Dec, FY27 by quarter, cash-goes-negative date, covenant headroom, runway,
and the revenue bridge from $12.0M to the target.

**3 · The memo.** The AI-written CFO decision memo for the active scenario. Regenerates
per scenario; warns you when the scenario has moved since the memo was written.

A real, unedited memo for the plan of record is checked in at
[`docs/05-reference-memo.md`](docs/05-reference-memo.md), with the scenario it was
generated from and a snippet to reproduce it. Every figure in it was verified back
against the model.

## The Plan Integrity Check

Six deterministic rules, surfaced on Screens 1, 2 and 3. The narrative layer is required
by its system prompt to address every flag that fires, and a flagged plan is never
described as healthy.

| Rule | Fires when |
|---|---|
| `bookings_capacity_vs_target` | Modeled Q4 net-new MRR falls short of the $350K the FY27 ramp requires |
| `at_risk_renewals_assumed_renewed` | The forecast carries the $42K November enterprise renewals as closing |
| `covenant_breach` | Cash falls below the $3.0M minimum-cash covenant in any scenario month |
| `hiring_ahead_of_capacity_evidence` | Planned AE production exceeds 2× the trailing actual net-new MRR run rate |
| `acquisition_draw_vs_min_cash` | The purchase-price cash outlay puts cash under the covenant floor at close |
| `quota_assumption_unvalidated_over_fy27` | The AE quota held as a run rate carries FY27 more than 20% past the board target |

**Three fire on the bundled data with no lever touched:**

1. **AE timing.** The FY27 ramp requires $350K of net-new MRR in Q4 2026. The plan
   produces **$33K**. The 4 AEs start December 1; on a 3-month ramp they contribute
   **$0** in Q4. Full productivity by October required a July 1 start — five months
   earlier than planned. Pulling the starts to October still yields only $87K, because
   the ramp cannot be recovered inside the quarter. The target and the hiring plan
   contradict each other, and no start date inside the window reconciles them.
2. **At-risk renewals.** $42K of enterprise MRR across two logos is flagged for the
   November renewal, and the base forecast carries all of it as renewing — $504K of ARR
   in the plan with no coverage.
3. **Hiring ahead of evidence.** Trailing three-month actual net-new MRR is **$14.9K per
   month company-wide** — below a *single* AE's $22K quota. The plan adds 4 AEs at $88K
   per month of assumed fully-ramped production: a 5.9× step-up with nothing in the
   actuals supporting it.

Two more fire when you turn the acquisition on: closing Brightpath at $7.5M takes cash
from $7.77M to **$269K** on the day of close, $2.73M below the covenant floor, and the
undrawn line is only $500K — so the structure has to change, not the draw.

## Model rules

- **Revenue.** Customers × ARPU by tier. Churn applied to the base, then new logos added
  and split by the August installed-base tier mix (88.5% Core / 11.5% Enterprise). NRR is
  applied as *expansion only* — a monthly factor of `1.05^(1/12)` on ARPU — with churn
  modeled separately so it is not double-counted. The price increase hits **at renewal
  only**: 1/12 of the base reprices each month from Oct 1, phasing the uplift in over
  twelve months. AE-sourced net-new MRR is a layer on top, subject to the same churn.
- **AE ramp.** An AE in tenure month *k* produces `min((k−1)/3, 1) × $22K`. A July 1 start
  is fully productive October 1; a December 1 start produces nothing in Q4.
- **Costs.** Payroll from the August base, plus $16.5K/month per AE from the start date,
  plus a company-wide 4% merit increase in January 2027. Other opex carried at trend
  (below). Interest is drawn debt × 11% ÷ 12, and rises if the line is drawn for the
  acquisition.
- **Cash.** `prior cash − net burn − one-time items`, where net burn = opex − MRR. This
  is the same convention the actuals use and it reproduces the stated position exactly:
  trailing-3-month burn of $455K against $8.7M of cash gives **19.1 months** of runway.
- **Acquisition.** Adds Brightpath MRR ($266.7K at close) decaying at `0.85^(1/12)`
  monthly to 85% over a year; adds $180K/month of opex less three redundant roles from
  month 3; spreads $400K of integration cost over six months; takes the purchase price
  out of cash, less up to $500K optionally drawn from the undrawn line; and accumulates
  +$25K MRR/month of cross-sell from month 7.

## Model simplifications

Consistency was the requirement, not precision. These are the deliberate simplifications:

1. **Cash collections ≈ MRR.** No AR/AP timing, no DSO, no deferred-revenue mechanics.
   Net burn is opex minus MRR in the month. This matches how the bundled actuals were
   built, so actuals and forecast are on one basis. Deferred revenue and AR are carried
   in the CSV but not used in the cash model.
2. **NRR is treated as gross expansion.** The 105% NRR lever is applied as an uplift on
   existing ARPU, with logo churn modeled separately. In a real model NRR is net of
   churn; splitting them keeps each lever independently meaningful but means the two
   are not additive to a reported NRR.
3. **Renewals are spread evenly.** The price increase phases in at 1/12 of the base per
   month from Oct 1 rather than following a real renewal calendar.
4. **Fractional customers.** The customer count is continuous, not integer — 12 new logos
   split 88.5/11.5 gives fractional counts by tier. This avoids rounding artefacts in the
   monthly roll-forward.
5. **New-logo tier mix is fixed** at the August installed-base ratio and does not shift
   with the AE plan.
6. **AE-sourced MRR is a separate layer**, not converted into customer counts. It churns
   at the blended logo-churn rate but carries no ARPU or tier of its own.
7. **AE productivity is flat after ramp.** Quota is held as a perpetual monthly rate with
   no decay, no attrition, and no territory saturation. This is what makes FY27 overshoot
   the board target — rule 6 exists to name that rather than hide it.
8. **Opex trend is mechanical.** Hosting, software and office/G&A extrapolate linearly on
   their Jan–Aug slope; marketing, travel/events and professional services are lumpy and
   carry at their eight-month mean. No seasonality, no step functions.
9. **Base headcount is flat** outside the AE plan. Only AE hires change payroll, plus the
   January 2027 merit increase.
10. **Redundancy savings are pro-rata.** Three of Brightpath's fourteen roles are costed
    at 3/14 of its $180K monthly opex, since no per-role cost is given.
11. **Acquisition retention is a smooth decay.** 85% gross retention is read as an annual
    rate applied monthly, rather than a one-time haircut at close.
12. **No taxes, no working-capital movements, no FX, no purchase accounting.** The
    acquisition is modeled as a cash outflow plus an operating book, not a balance sheet.
13. **Runway is cash ÷ trailing-3-month average burn** at the measurement month, held
    flat. It does not re-solve forward against an improving burn curve.

## A note on what the model says

The base case exits FY26 at **$12.56M** against the $13.5M target — $936K short. The tool
reports that rather than the "on pace" framing, because that is what the arithmetic gives
at the current run rate. The FY27 number is more than the board target for the reason in
simplification 7 and rule 6: the $22K AE quota is calibrated to just cover a Q4 sprint,
and holding it as a run rate for a year produces roughly twice the plan. Both cannot be
true. The tool names the contradiction instead of picking whichever answer is more
comfortable.

## How this was built

The full record is in [`docs/07-chat-history.md`](docs/07-chat-history.md) —
thirty-nine exchanges across two sessions and three days. Part 1 is the research
and problem definition that chose this build over nine alternatives and vetted
each against shipping products; Part 2 is the Claude Code session that built,
reviewed and hardened it.

Supporting documents:

| | |
|---|---|
| [`docs/01-process-timeline.md`](docs/01-process-timeline.md) | How the project ran, start to submission |
| [`docs/02-problem-statement.md`](docs/02-problem-statement.md) | The problem, why it persists, who has it |
| [`docs/03-idea-funnel.md`](docs/03-idea-funnel.md) | Ten ideas in, one out, with the vendor that killed each |
| [`docs/05-build-decisions.md`](docs/05-build-decisions.md) | Judgement calls made during the build, and why |
| [`docs/06-work-list.md`](docs/06-work-list.md) | The usability pass, verified against the model |
| [`docs/research/`](docs/research/) | ICP report, vendor vetting, idea ledger |

## Chart design notes

Colors are assigned by the job they do, not cycled: blue is always actuals, orange
always forecast, and the same entity keeps its color across all three screens. Status
colors (breach red, at-risk amber) are reserved and never reused as a series color, and
always ship with a label rather than carrying meaning through color alone.

The categorical palette was validated for colorblind separation rather than eyeballed —
worst adjacent CVD ΔE 23.1 and normal-vision ΔE 24.0 on the three-series stack, both
clear of the floors. The one contrast warning (the aqua at 2.74:1 against the light
surface) carries a relief obligation, met in both places it appears: the revenue bridge
direct-labels every bar, and the MRR composition chart sits immediately above the full
monthly forecast table.

The app pins Streamlit's light theme in `.streamlit/config.toml`, because the palette and
the custom CSS are validated against the light surface (`#fcfcfb`). Without the pin the
app would inherit the reviewer's OS appearance setting and render dark chrome under a
light-designed chart layer.
