"""The AI narrative layer.

The model receives computed metrics as structured JSON and writes prose. It never
calculates, and it is given no raw data to calculate from — only results. The
system prompt is the one in SYSTEM_PROMPT.md, kept in sync here.
"""
from __future__ import annotations

import json
import os

import anthropic

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are Floyd, an AI operating partner for CFOs of high-growth, recurring-revenue companies.

Your job is to turn the structured outputs of a deterministic financial model into a concise, board-ready decision memo. You do not calculate metrics, alter numbers, invent facts, or give accounting, tax, legal, or investment advice.

Use only the supplied structured inputs: current actuals, scenario settings, forecast results, covenant status, and integrity-check flags. If an input is missing or inconsistent, name the limitation. Never fill a gap by inference.

Your memo must:
1. State whether the company is on track for its revenue target, with the number.
2. Explain the two to four drivers that most determine the outcome.
3. Assess cash, runway, covenant, retention, and execution risk for the active scenario.
4. Address every integrity-check flag explicitly. A flagged plan is never described as healthy.
5. Distinguish facts, assumptions, and recommendations. Label them.
6. Recommend one specific decision, with the leading indicators to watch and the thresholds that should trigger a change of course.
7. Stay concise and direct, written for a CFO, CEO, and board audience.

Structure:
- Executive readout (three sentences maximum)
- What changed / key drivers
- Scenario and risk assessment
- Plan integrity
- Recommended decision
- Leading indicators and triggers

Calibrated language only: "the model indicates," "under the stated assumptions," "the plan depends on." Never present a forecast as certainty. Never soften a covenant breach or an integrity flag."""

USER_TEMPLATE = """Write the CFO decision memo for the scenario below.

All figures are USD. Every number in this payload was computed by the deterministic model; use these values and do not derive new ones. Format the memo in Markdown using the six required section headings.

```json
{payload}
```"""


class NarrativeError(RuntimeError):
    pass


def assumptions_in_force(scenario, defaults, actuals) -> list[dict]:
    """Every assumption this scenario carries that is not evidence from the books.

    Three levers on this tool are judgement rather than measurement, and a
    scenario that moves them can reach almost any answer. Listing them beside
    the result is what stops a set of choices being laundered into a
    recommendation: the memo has to say what it assumed to get there.
    """
    out = []
    arpu = actuals.blended_arpu

    logos = scenario.ae_quota_net_new_mrr / arpu
    plan_logos = defaults.ae_quota_net_new_mrr / arpu
    out.append({
        "assumption": "AE productivity once ramped",
        "value": f"{logos:.1f} new logos per rep per month (${scenario.ae_quota_net_new_mrr:,.0f} MRR)",
        "board_plan": f"{plan_logos:.1f} logos per rep per month",
        "at_board_plan": abs(logos - plan_logos) < 0.05,
        "basis": (
            "Judgement. Copperline has never recorded production per rep — there is no AE "
            f"headcount in the books — so no per-rep rate can be derived. For scale, the "
            f"whole company lands {actuals.new_logos_trailing_3mo:.0f} logos a month."
        ),
    })

    out.append({
        "assumption": "Customers lost to a price increase",
        "value": (f"{scenario.price_churn_sensitivity:.1f}% of each repricing cohort per point "
                  f"of increase" if scenario.price_increase_pct > 0 else "not engaged (no increase)"),
        "board_plan": "no increase is planned, so the question does not arise",
        "at_board_plan": scenario.price_increase_pct == 0,
        "basis": (
            "Judgement. No past price change appears in the data, so there is no elasticity "
            "to fit. Zero would mean revenue rising with nobody objecting."
        ),
    })

    out.append({
        "assumption": "Undrawn debt facility",
        "value": f"${scenario.debt_facility:,.0f} available to draw",
        "board_plan": f"${defaults.debt_facility:,.0f} (the figure in the supplied data)",
        "at_board_plan": scenario.debt_facility == defaults.debt_facility,
        "basis": "Supplied data at the default. Anything above it is a facility not yet negotiated.",
    })
    return out


def build_payload(
    actuals,
    scenario,
    metrics: dict,
    flags: list,
    fy27_quarters: list[dict],
    bridge: list[dict],
    defaults=None,
) -> dict:
    """Assemble the structured JSON the model writes from. Numbers only, no prose math."""
    disclosure = (
        assumptions_in_force(scenario, defaults, actuals) if defaults is not None else []
    )
    return {
        "assumptions_in_force": {
            "note": (
                "Judgement calls this scenario rests on, not measurements. State any that "
                "differ from the board plan in the memo; a recommendation that depends on "
                "one of these has to say so."
            ),
            "any_departures_from_board_plan": any(not d["at_board_plan"] for d in disclosure),
            "items": disclosure,
        },
        "company": {
            "name": "Copperline",
            "profile": "Series B B2B SaaS, workflow software",
            "as_of": actuals.last_month,
        },
        "actuals_through_august_2026": {
            "arr": round(actuals.arr),
            "mrr": round(actuals.mrr),
            "customers": actuals.customers,
            "core_customers": actuals.core_customers,
            "enterprise_customers": actuals.enterprise_customers,
            "core_arpu_monthly": round(actuals.core_arpu),
            "enterprise_arpu_monthly": round(actuals.enterprise_arpu),
            "headcount": actuals.headcount,
            "cash": round(actuals.cash),
            "net_burn_last_month": round(actuals.net_burn_last),
            "net_burn_trailing_3mo_avg": round(actuals.net_burn_trailing_3mo),
            "runway_months_at_current_burn": round(actuals.runway_months, 1),
            "mrr_growth_last_month_pct": round(actuals.arr_growth_mom_pct, 2),
            "net_new_mrr_per_month_trailing_3mo": round(actuals.net_new_mrr_trailing_3mo),
        },
        "scenario_settings": scenario.as_dict(),
        "forecast_results": {
            "fy26_exit_arr": round(metrics["fy26_exit_arr"]),
            "fy26_target_arr": round(metrics["fy26_target"]),
            "fy26_variance_to_target": round(metrics["fy26_variance"]),
            "fy27_exit_arr": round(metrics["fy27_exit_arr"]),
            "fy27_target_arr": round(metrics["fy27_target"]),
            "fy27_variance_to_target": round(metrics["fy27_variance"]),
            "q4_2026_net_new_mrr_modeled": round(metrics["q4_2026_net_new_mrr"]),
            "q4_2026_net_new_mrr_required": round(metrics["q4_2026_net_new_mrr_required"]),
            "q4_2026_net_new_mrr_from_new_aes": round(metrics["q4_2026_ae_contribution_mrr"]),
            "dec_2026_cash": round(metrics["dec_2026_cash"]),
            "dec_2027_cash": round(metrics["dec_2027_cash"]),
            "avg_monthly_net_burn_q4_2026": round(metrics["avg_monthly_burn_q4_2026"]),
            "runway_months_from_dec_2026": (
                None
                if metrics["runway_months_from_dec_2026"] == float("inf")
                else round(metrics["runway_months_from_dec_2026"], 1)
            ),
            "cash_goes_negative_month": metrics["cash_goes_negative_month"],
            "fy27_by_quarter": fy27_quarters,
            "revenue_bridge_aug_2026_to_dec_2026_arr": [
                {"component": c["label"], "arr_impact": round(c["value"])} for c in bridge
            ],
        },
        "covenant_status": {
            "minimum_cash_covenant": round(metrics["covenant"]["min_cash_covenant"]),
            "trough_cash": round(metrics["covenant"]["trough_cash"]),
            "trough_month": metrics["covenant"]["trough_month"],
            "headroom_at_trough": round(metrics["covenant"]["headroom"]),
            "breach": metrics["covenant"]["breach"],
            "first_breach_month": metrics["covenant"]["first_breach_month"],
            "months_in_breach": len(metrics["covenant"]["breach_months"]),
        },
        "integrity_check_flags": [f.to_dict() for f in flags],
    }


def _load_dotenv() -> None:
    """Read KEY=value pairs from a local .env into the environment.

    Deliberately hand-rolled rather than taking a python-dotenv dependency, so the
    stated setup stays `pip install -r requirements.txt` and nothing else. A project
    -local .env is preferred over exporting ANTHROPIC_API_KEY globally, which would
    also redirect every other tool on the machine to this key.

    Values already present in the environment win, so an explicit export still
    overrides the file.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # An unreadable .env is not fatal — the sidebar field still works.
        pass


_load_dotenv()


def _client(api_key: str | None = None) -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise NarrativeError(
            "No API key found. Put ANTHROPIC_API_KEY in a .env file next to app.py, "
            "export it in your environment, or paste a key in the sidebar."
        )
    return anthropic.Anthropic(api_key=key)


def generate_memo(payload: dict, api_key: str | None = None) -> str:
    """Call Claude for the memo. Returns Markdown."""
    client = _client(api_key)
    message = USER_TEMPLATE.format(payload=json.dumps(payload, indent=2, default=float))

    request = dict(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
        output_config={"effort": "high"},
    )
    minimal = {k: v for k, v in request.items() if k != "output_config"}

    # Preferred call first, then progressively plainer ones so an older SDK still works.
    # Server-side fallback: if safety classifiers decline, Anthropic re-runs the request
    # on the recommended fallback model inside the same call.
    attempts = [
        lambda: client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
        ),
        lambda: client.messages.create(**request),
        lambda: client.messages.create(**minimal),
    ]

    response = None
    for i, attempt in enumerate(attempts):
        try:
            response = attempt()
            break
        except anthropic.AuthenticationError as exc:
            raise NarrativeError("The API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise NarrativeError("Rate limited by the API. Wait a moment and regenerate.") from exc
        except anthropic.APIConnectionError as exc:
            raise NarrativeError("Could not reach the API. Check your network connection.") from exc
        except (TypeError, AttributeError):
            # Client-side signature mismatch on an older SDK — try the plainer call.
            if i == len(attempts) - 1:
                raise NarrativeError(
                    "This anthropic SDK version does not accept the request parameters. "
                    "Upgrade with: pip install -U anthropic"
                )
        except anthropic.BadRequestError as exc:
            msg = str(getattr(exc, "message", exc) or exc)
            low = msg.lower()
            if "credit balance" in low or "billing" in low:
                raise NarrativeError(
                    "The API key is valid, but the account has no credit balance, so the "
                    "request was rejected. Add credits under Plans & Billing at "
                    "console.anthropic.com, then regenerate. Screens 1 and 2 are unaffected."
                ) from exc
            # Only a parameter-shape rejection is worth retrying on a plainer call;
            # anything else is a real rejection and should surface immediately rather
            # than burning two more requests on the same failure.
            retryable = any(
                s in low for s in ("unexpected keyword", "unknown parameter", "extra inputs",
                                   "unrecognized", "unexpected_value", "not supported")
            )
            if retryable and i < len(attempts) - 1:
                continue
            raise NarrativeError(f"The API rejected the request: {msg}") from exc
        except anthropic.APIStatusError as exc:
            raise NarrativeError(f"API error {exc.status_code}: {exc.message}") from exc

    if response.stop_reason == "refusal":
        raise NarrativeError(
            "The model declined to answer this request. The deterministic figures and the "
            "integrity check on this screen are unaffected."
        )

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise NarrativeError("The model returned an empty memo. Try regenerating.")
    return text
