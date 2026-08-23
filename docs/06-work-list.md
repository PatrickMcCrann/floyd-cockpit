# Work List — usability and model-transparency pass

Prioritised from a review session on 2026-08-22. Ordered by what a reviewer hits
first, with broken-before-polish as the tiebreaker.

Every claim in here was verified against the model, not eyeballed. The numbers
quoted are reproducible from `run_forecast` on the plan of record.

**Status: every item is done except the ramp judgement in P0-1, which is a
modelling call rather than a fix and is left to the owner.**

Deployment note: a source-only push can leave Streamlit Cloud running new
`app.py` against a cached `charts.py`, which threw `TypeError` on Screen 2 while
Screen 1 looked fine. Reboot from the dashboard, or touch `requirements.txt` to
force an environment rebuild — and verify on a screen that exercises the changed
module, not just the landing page.

Effort: `S` under 30 min · `M` 1–2 h · `L` half day+

---

## P0 — Broken or actively misleading

### [~] 1. The AE hires lever is inert under the plan of record `S` — *partly addressed*

Moving the slider from 0 to 10 hires produces **byte-identical FY26 ARR**.
Only cash moves, and only downward — so the flagship lever reads as pure cost
with zero benefit.

| AE hires | FY26 exit ARR | Dec 2026 cash |
|---|---|---|
| 0 | $12,564,341 | $7,005,725 |
| 4 | $12,564,341 | $6,939,725 |
| 10 | $12,564,341 | $6,840,725 |

Two causes stack:

- The plan of record starts AEs **2026-12**, the last month in the FY26 view.
- `_ae_ramp_fraction` (`model.py:169`) returns **0.00 for tenure month 1**.
  The ramp is 0.00 / 0.33 / 0.67 / 1.00 across months 1–4.

So a December start yields zero AE revenue inside FY26 by construction. Move the
start to September and 10 hires takes FY26 ARR to **$17.78M**.

**Done:** the sidebar now warns that a rep books nothing in month 1, so a late
start contributes nothing to FY26; and the baseline overlay (P2-11) renders a
zero delta as two lines sitting on top of each other rather than as nothing
happening.

**Still open, and it is your call:** whether ramp month 1 should really be 0.00.
That is a modelling judgement, not a bug — a rep genuinely may book nothing in
their first month. Left as-is deliberately.

### [x] 2. "Net burn (3-mo avg)" on Screen 1 can never change `S`

`app.py:317` renders `actuals.net_burn_trailing_3mo` — the trailing average of
**actuals** (Jun–Aug 2026). No lever can move it, ever. It sits beside live
controls, so it reads as a broken live number.

**Do:** relabel to "Net burn (last 3 months, actual)". Forecast burn does respond
correctly — Dec 2026 goes $410K → $575K between 0 and 10 hires, exactly
10 × $16,500 — but that figure only appears in the monthly table.

### [x] 3. Revenue-up and covenant-broken must read as one fact `M`

**The single most important item on this list.** Acquiring Brightpath at the
asking price:

- FY26 exit ARR **$12.56M → $15.72M** — it *beats* the $13.5M board target
- December 2026 cash: **−$523,862**
- Covenant breached for **14 consecutive months** from 2026-11
- Cash trough **−$1.79M** in 2027-05

The good news and the fatal news currently sit in different places at equal
visual weight. A reviewer sees revenue up $3M and feels good. This tension is the
entire thesis of the product and it is the worst-communicated thing on screen.

**Do:** when a scenario breaches, the breach owns the headline. Revenue gain is
subordinate to it, not adjacent.

---

## P1 — Structure: three screens, three jobs

Screen 1 is a fixed baseline. Screen 2 is where things move. Screen 3 publishes.

### [x] 4. Remove the levers from Screen 1 `S`

Levers live in a global sidebar visible on every screen. Screen 1 is built from
historical actuals, so moving a control there changes nothing — correct
behaviour that feels broken. This is the root cause of the confusion.

### [x] 5. Framing paragraph at the top of Screen 1 `S`

Who built this, who it is for, what decision is on the table, and that the levers
come next. Roughly:

> This is a forecasting tool built by Copperline's CFO to help the leadership team
> and board make one decision. Eight months of FY26 actuals are on the books.
> The board wants $13.5M exit ARR this year and $18M next. As you weigh hiring
> against acquiring, this page is where we stand today — the fixed starting point.
> The Decision Studio is where you change it.

### [x] 6. Move the AE start date to Screen 2 and give it weight `S`

It is the master switch that makes hiring mean anything (see P0-1), not just
another slider in the stack.

### [x] 7. Show the starting assumptions on Screen 1 `M`

You cannot evaluate a deal whose price you have never been shown. Screen 1 needs
the givens, including everything in P1-8 and P1-9 below.

### [x] 8. Financing panel on Screen 1 — the debt is invisible `M`

Interest **is** correctly inside the burn: `total_opex = payroll + other_opex +
interest + acq_opex + integration` (`model.py:325`), so the math is right. But
`app.py` mentions debt exactly once — the "funded from the undrawn line" slider.
The company is paying for this facility and cannot see it.

Surface, as stated facts:

| | |
|---|---|
| Term loan drawn | $4,000,000 |
| Rate | 11%, interest-only through 2027 |
| Interest cost | **$36,667/mo · $440,000/yr** (already inside net burn) |
| Undrawn remaining | $500,000 |
| Minimum-cash covenant | $3,000,000 |

Also state the financing posture explicitly: **this tool does not model a new
equity round.** That gives the bootstrapped-feeling constraint without
contradicting the brief's Series B framing, which the venture debt implies.

### [x] 9. Brightpath callout box on Screen 1, and in the memo `M`

All of this is in the CSV and none of it is shown:

| | |
|---|---|
| Asking price | $7,500,000 |
| Trailing ARR | $3,200,000 → **2.34× ARR** |
| Gross retention | 85% → $2.72M retained → **2.76× retained ARR** |
| Acquired opex | $180,000/mo ($2.16M/yr) |
| Headcount | 14, of which 3 redundant from month 3 |
| Integration | $400,000 over 6 months |
| Cross-sell | +$25,000 MRR/mo from month 7 |
| Closes | 2026-11-01 |

Lead the box with the payback line, which is the sentence a CFO reviewer will
look for and not currently find:

> Retained revenue $2.72M/yr against $2.16M/yr of acquired opex is **$560K/yr of
> contribution before synergies**. After eliminating 3 redundant roles and
> layering in cross-sell, roughly **$1.45M/yr** — a **~5-year payback** on $7.5M.

### [x] 10. Show that cash is spoken for `M`

Cash can rise in year one while being fully committed to the acquisition, and
nothing on screen says so. A reader who is not a finance specialist reads the
balance as available. Distinguish **cash balance** from **uncommitted cash** —
balance less the covenant floor, less committed acquisition and integration
outflows — so "we have money" and "we can spend money" stop looking identical.

---

## P2 — Charts

### [x] 11. Keep the plan of record on screen, and re-map the colours `M`

Highest-leverage visual change on the list: it makes every lever
self-explanatory, because you can always see what you changed *from*.

| Line | Meaning | Treatment |
|---|---|---|
| Actuals | What happened | Blue, solid, markers |
| Plan-of-record forecast | Where today's plan takes us — the reference | **Blue, dotted** |
| Active scenario | What your levers did | **Orange, solid** |

Blue is the status quo, past and projected. Orange is the intervention. This is
also why "forecast versus predicted" felt slippery: orange currently means
*future*, so the instant a lever moves it has to mean two things at once.

---

## P3 — Model realism

### [x] 12. Make the facility size an adjustable input, default $500K `M`

$500K of undrawn capacity against $12M ARR and $8.7M cash is thin, and it makes
the financing lever nearly meaningless — you cannot explore borrow-versus-don't
inside $500K. Expose it as an input rather than silently overwriting it: that
keeps faith with the supplied dataset while making the choice real.

Pair it with a cost-of-debt readout — amount drawn, monthly interest, cumulative
interest through the horizon — so borrowing has a visible price.

---

## P4 — The feedback layer

### [x] 13. Always-on plain-language readout on Screen 2 `M`

There is a gap between moving a slider and generating a memo: the memo costs
money and takes seconds, so nobody generates one per toggle. A live one-liner
("this breaches the covenant in November") fills it, and the memo stays the
deliberate, publishable artifact.

---

## Decisions taken in this review

- **Series B framing stays.** The $4M venture term loan at 11% is a
  venture-backed instrument and a CFO reviewer would notice a bootstrapped story
  wrapped around it. The constraint that was actually wanted — no rescue capital
  — is stated directly instead: *this tool does not model a new equity round.*
- **Supplied numbers are not overwritten.** Anything that deviates from the
  provided dataset becomes an adjustable input with the original as its default,
  and is labelled. Reviewers gave us that data and can diff against it.
- **AE hires and new logos stay uncoupled.** Auto-driving logos from headcount
  would remove the ability to model "we hired and they underperformed," which is
  the risk a CFO actually cares about. The fix is to make AE-sourced revenue a
  visible line, not to couple the inputs.

## Verified against the model

Reproduce with `run_forecast` on the plan of record:

- Sept 2026 opex: payroll $1,048,000 · other $365,911 · interest $36,667 ·
  total $1,450,577 · net burn $436,783
- Interest is inside `total_opex`, therefore inside `net_burn` — confirmed
- AE ramp fractions, tenure months 1–4: 0.00 / 0.33 / 0.67 / 1.00
- 10 AEs × $16,500 = $165,000/mo, matching the December payroll step exactly
