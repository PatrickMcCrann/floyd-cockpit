"""Plotly figures.

One shared palette and one shared layout so every chart on every screen reads as
the same system. Colors are assigned by the job they do (identity, polarity,
status), never cycled, and the same entity keeps the same color across screens.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Categorical slots, in fixed order — validated for CVD separation as a set.
BLUE = "#2a78d6"      # slot 1 — the status quo: actuals, and where the plan of record leads
ORANGE = "#eb6834"    # slot 2 — the intervention: the scenario the user built
AQUA = "#1baf7a"      # slot 3
YELLOW = "#eda100"    # slot 4
MAGENTA = "#e87ba4"   # slot 5
VIOLET = "#4a3aa7"    # slot 7

# Status — reserved, never reused as a series color.
GOOD = "#0ca30c"
WARNING = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"

# Chrome and ink.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def _base_layout(fig: go.Figure, height: int = 340, ylabel: str = "") -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=28, b=8),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12, color=INK_2),
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
    )
    fig.update_xaxes(
        showgrid=False, linecolor=BASELINE, ticks="outside", tickcolor=BASELINE,
        tickfont=dict(color=MUTED, size=11),
    )
    fig.update_yaxes(
        gridcolor=GRID, zeroline=False, linecolor="rgba(0,0,0,0)",
        tickfont=dict(color=MUTED, size=11), title=dict(text=ylabel, font=dict(color=MUTED, size=11)),
    )
    return fig


def _bridged(act: pd.DataFrame, fc: pd.DataFrame, col: str) -> pd.DataFrame:
    """Forecast rows preceded by the last actual, so the line has no gap at the handoff."""
    return pd.concat([act.tail(1), fc], ignore_index=True)[["month", col]]


def arr_trajectory(
    series: pd.DataFrame,
    fy26_target: float,
    fy27_target: float,
    baseline: pd.DataFrame | None = None,
) -> go.Figure:
    """ARR over time.

    Colour carries meaning and is consistent across every chart in the app:
    blue is the status quo — what actually happened, and where the present day plan
    leads if nobody intervenes. Orange is the intervention, the scenario the user
    built. Pass `baseline` (a present-day-plan series) to keep the do-nothing path
    on screen as a blue dotted reference, so the delta a lever produced is visible
    rather than remembered.
    """
    act = series[series["kind"] == "actual"]
    fc = series[series["kind"] == "forecast"]
    bridge = _bridged(act, fc, "arr")
    has_baseline = baseline is not None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=act["month"], y=act["arr"] / 1e6, name="Actual ARR", mode="lines+markers",
        line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE),
        hovertemplate="%{x}<br>$%{y:.2f}M<extra>Actual</extra>",
    ))
    if has_baseline:
        b_act = baseline[baseline["kind"] == "actual"]
        b_fc = baseline[baseline["kind"] == "forecast"]
        b = _bridged(b_act, b_fc, "arr")
        fig.add_trace(go.Scatter(
            x=b["month"], y=b["arr"] / 1e6, name="Present day plan", mode="lines",
            line=dict(color=BLUE, width=2, dash="dot"),
            hovertemplate="%{x}<br>$%{y:.2f}M<extra>Present day plan</extra>",
        ))
    fig.add_trace(go.Scatter(
        x=bridge["month"], y=bridge["arr"] / 1e6,
        name="This scenario" if has_baseline else "Present day plan", mode="lines",
        line=dict(
            color=ORANGE if has_baseline else BLUE,
            width=2, dash="solid" if has_baseline else "dot",
        ),
        hovertemplate="%{x}<br>$%{y:.2f}M<extra>"
                      + ("This scenario" if has_baseline else "Forecast") + "</extra>",
    ))
    for target, label in ((fy26_target, "FY26 target $13.5M"), (fy27_target, "FY27 target $18.0M")):
        fig.add_hline(
            y=target / 1e6, line=dict(color=MUTED, width=1, dash="dot"),
            annotation_text=label, annotation_position="top left",
            annotation_font=dict(color=MUTED, size=11),
        )
    return _base_layout(fig, ylabel="ARR ($M)")


def cash_and_covenant(
    series: pd.DataFrame, floor: float, baseline: pd.DataFrame | None = None
) -> go.Figure:
    """Cash against the covenant floor. Breach months are marked, not implied.

    See `arr_trajectory` for the colour rule. `baseline` overlays the present day
    plan so the cash cost of a decision is visible as a gap, not a memory.
    """
    act = series[series["kind"] == "actual"]
    fc = series[series["kind"] == "forecast"]
    bridge = pd.concat([act.tail(1), fc], ignore_index=True)
    has_baseline = baseline is not None

    # Shade only down to just below the actual data, so the axis is not padded out to
    # a negative floor the scenario never reaches.
    lowest = float(series["cash"].min())
    if has_baseline:
        lowest = min(lowest, float(baseline["cash"].min()))
    low = min(lowest / 1e6, floor / 1e6) - 0.4
    fig = go.Figure()
    fig.add_hrect(
        y0=low, y1=floor / 1e6,
        fillcolor=CRITICAL, opacity=0.07, line_width=0, layer="below",
    )
    fig.add_trace(go.Scatter(
        x=act["month"], y=act["cash"] / 1e6, name="Cash (actual)", mode="lines+markers",
        line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE),
        hovertemplate="%{x}<br>$%{y:.2f}M<extra>Actual</extra>",
    ))
    if has_baseline:
        b = pd.concat([baseline[baseline["kind"] == "actual"].tail(1),
                       baseline[baseline["kind"] == "forecast"]], ignore_index=True)
        fig.add_trace(go.Scatter(
            x=b["month"], y=b["cash"] / 1e6, name="Present day plan", mode="lines",
            line=dict(color=BLUE, width=2, dash="dot"),
            hovertemplate="%{x}<br>$%{y:.2f}M<extra>Present day plan</extra>",
        ))
    fig.add_trace(go.Scatter(
        x=bridge["month"], y=bridge["cash"] / 1e6,
        name="This scenario" if has_baseline else "Present day plan", mode="lines",
        line=dict(
            color=ORANGE if has_baseline else BLUE,
            width=2, dash="solid" if has_baseline else "dot",
        ),
        hovertemplate="%{x}<br>$%{y:.2f}M<extra>"
                      + ("This scenario" if has_baseline else "Forecast") + "</extra>",
    ))
    breach = fc[fc["cash"] < floor]
    if not breach.empty:
        fig.add_trace(go.Scatter(
            x=breach["month"], y=breach["cash"] / 1e6, name="Covenant breach", mode="markers",
            marker=dict(size=10, color=CRITICAL, line=dict(width=2, color=SURFACE)),
            hovertemplate="%{x}<br>$%{y:.2f}M — below floor<extra>Breach</extra>",
        ))
    fig.add_hline(
        y=floor / 1e6, line=dict(color=CRITICAL, width=2),
        annotation_text=f"Covenant floor ${floor / 1e6:.1f}M", annotation_position="bottom left",
        annotation_font=dict(color=CRITICAL, size=11),
    )
    return _base_layout(fig, ylabel="Cash ($M)")


def burn_chart(series: pd.DataFrame, baseline: pd.DataFrame | None = None) -> go.Figure:
    """Monthly net burn. See `arr_trajectory` for the colour rule.

    Bars carry the same meaning as the lines: blue is the status quo, orange is
    the intervention. Filled means observed or chosen; hollow means projected —
    the bar equivalent of a dotted line. A diagonal hatch was tried here first
    and read as an empty bar at chart scale.
    """
    act = series[series["kind"] == "actual"]
    fc = series[series["kind"] == "forecast"]
    has_baseline = baseline is not None
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=act["month"], y=act["net_burn"] / 1e3, name="Net burn (actual)",
        marker=dict(color=BLUE, line=dict(width=2, color=SURFACE)),
        hovertemplate="%{x}<br>$%{y:,.0f}K<extra>Actual</extra>",
    ))
    if has_baseline:
        b_fc = baseline[baseline["kind"] == "forecast"]
        fig.add_trace(go.Bar(
            x=b_fc["month"], y=b_fc["net_burn"] / 1e3, name="Present day plan",
            marker=dict(color="rgba(42,120,214,0.18)", line=dict(width=1.5, color=BLUE)),
            hovertemplate="%{x}<br>$%{y:,.0f}K<extra>Present day plan</extra>",
        ))
        fig.add_trace(go.Bar(
            x=fc["month"], y=fc["net_burn"] / 1e3, name="This scenario",
            marker=dict(color=ORANGE, line=dict(width=1.5, color=SURFACE)),
            hovertemplate="%{x}<br>$%{y:,.0f}K<extra>This scenario</extra>",
        ))
    else:
        fig.add_trace(go.Bar(
            x=fc["month"], y=fc["net_burn"] / 1e3, name="Present day plan",
            marker=dict(color="rgba(42,120,214,0.18)", line=dict(width=1.5, color=BLUE)),
            hovertemplate="%{x}<br>$%{y:,.0f}K<extra>Forecast</extra>",
        ))
    fig.update_layout(bargap=0.25, barmode="group")
    return _base_layout(fig, height=280, ylabel="Net burn ($K)")


def _bridge_label(v: float, kind: str) -> str:
    """Totals read as plain amounts; deltas carry an explicit sign."""
    sign = "" if kind == "total" else ("+" if v >= 0 else "\u2212")
    a = abs(v)
    return f"{sign}${a / 1e6:.2f}M" if a >= 1e6 else f"{sign}${a / 1e3:,.0f}K"


def revenue_bridge_chart(components: list[dict]) -> go.Figure:
    """Waterfall from opening ARR to closing ARR. Polarity is the color job here."""
    measure = ["absolute" if c["kind"] == "total" else "relative" for c in components]
    measure[-1] = "total"
    labels = [c["label"] for c in components]
    values = [c["value"] for c in components]

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measure,
        x=labels,
        y=values,
        text=[_bridge_label(v, k) for v, k in zip(values, [c["kind"] for c in components])],
        textposition="outside",
        textfont=dict(color=INK_2, size=11),
        connector=dict(line=dict(color=BASELINE, width=1)),
        increasing=dict(marker=dict(color=AQUA, line=dict(width=2, color=SURFACE))),
        decreasing=dict(marker=dict(color=CRITICAL, line=dict(width=2, color=SURFACE))),
        totals=dict(marker=dict(color=BLUE, line=dict(width=2, color=SURFACE))),
        hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(hovermode="closest")
    return _base_layout(fig, height=380, ylabel="ARR ($)")


def mrr_composition(fc: pd.DataFrame) -> go.Figure:
    """Where forecast MRR comes from: base book, AE-sourced, acquired."""
    fig = go.Figure()
    layers = [
        ("base_mrr", "Base book", BLUE),
        ("ae_mrr", "New AE capacity", AQUA),
        ("acquired_mrr", "Brightpath", VIOLET),
        ("at_risk_mrr", "At-risk renewals", CRITICAL),
    ]
    for col, name, color in layers:
        if fc[col].abs().sum() < 1.0:
            continue
        fig.add_trace(go.Bar(
            x=fc["month"], y=fc[col] / 1e3, name=name,
            marker=dict(color=color, line=dict(width=2, color=SURFACE)),
            hovertemplate="%{x}<br>$%{y:,.0f}K<extra>" + name + "</extra>",
        ))
    fig.update_layout(barmode="relative", bargap=0.25)
    return _base_layout(fig, height=320, ylabel="MRR ($K)")


def quarterly_fy27_chart(q: pd.DataFrame, target: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=q["quarter"], y=q["exit_arr"] / 1e6, name="Exit ARR",
        marker=dict(color=BLUE, line=dict(width=2, color=SURFACE)),
        text=[f"${v / 1e6:.2f}M" for v in q["exit_arr"]],
        textposition="outside", textfont=dict(color=INK_2, size=11),
        hovertemplate="%{x}<br>$%{y:.2f}M<extra>Exit ARR</extra>",
    ))
    fig.add_hline(
        y=target / 1e6, line=dict(color=MUTED, width=1, dash="dot"),
        annotation_text=f"FY27 target ${target / 1e6:.1f}M", annotation_position="top left",
        annotation_font=dict(color=MUTED, size=11),
    )
    fig.update_layout(hovermode="closest", bargap=0.4)
    return _base_layout(fig, height=300, ylabel="Exit ARR ($M)")
