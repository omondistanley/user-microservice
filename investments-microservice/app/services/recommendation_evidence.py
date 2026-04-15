"""
Build data-backed explanation fields for the recommendations explain API.
Non-advisory: describes scoring inputs, market snapshots, and preferences — not buy/sell orders.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.finance_context_client import FinanceContext


def _fmt_num(x: Any, digits: int = 2) -> str:
    try:
        return f"{float(x):.{digits}f}"
    except (TypeError, ValueError):
        return str(x) if x is not None else "—"


def finance_context_summary_lines(ctx: Optional[FinanceContext]) -> List[str]:
    if ctx is None:
        return []
    if not ctx.data_fresh:
        return ["Finance personalization: linked cashflow/goals data was unavailable or stale for this session."]
    lines: List[str] = []
    if ctx.income_total is not None and ctx.expense_total is not None:
        lines.append(
            f"Cashflow window: income ~${_fmt_num(ctx.income_total, 0)}, expenses ~${_fmt_num(ctx.expense_total, 0)} "
            f"(surplus ~${_fmt_num(ctx.surplus or 0, 0)})."
        )
    if ctx.savings_rate is not None:
        lines.append(f"Estimated savings rate over the window: {_fmt_num(ctx.savings_rate * 100, 1)}% of income.")
    if ctx.active_goals_count:
        lines.append(f"Active goals: {ctx.active_goals_count}.")
        if ctx.goal_horizon_months is not None:
            lines.append(f"Nearest goal horizon (approx.): {ctx.goal_horizon_months} months.")
        if ctx.goals_behind:
            lines.append(
                f"Some goals appear behind target ({ctx.goals_behind_count} flagged); scores tilt slightly more conservative per policy."
            )
    return lines


def preference_lines(risk: Optional[Dict[str, Any]]) -> List[str]:
    if not risk:
        return ["No saved risk profile was loaded; defaults (balanced) apply."]
    out: List[str] = []
    rt = risk.get("risk_tolerance") or "balanced"
    out.append(f"Risk tolerance setting: {rt}.")
    ind = risk.get("industry_preferences")
    if ind:
        if isinstance(ind, list):
            out.append(f"Sector/industry preferences: {', '.join(str(x) for x in ind)}.")
        else:
            out.append(f"Sector/industry preferences: {ind}.")
    la = risk.get("loss_aversion")
    if la:
        out.append(f"Loss aversion: {la}.")
    so = risk.get("sharpe_objective")
    if so is not None and str(so).strip():
        out.append(f"Target Sharpe objective (user): {_fmt_num(so)}.")
    if risk.get("use_finance_data_for_recommendations"):
        out.append("Personalization from savings, goals, expenses & budget is enabled for this account.")
    else:
        out.append("Personalization from savings/goals/budget is off; only portfolio and market inputs apply.")
    return out


def score_breakdown_lines(expl: Dict[str, Any]) -> List[str]:
    sb = expl.get("score_breakdown")
    if not isinstance(sb, dict):
        return []
    lines: List[str] = []
    desc = sb.get("description")
    if desc:
        lines.append(str(desc))
    for key, label in (
        ("heuristic_score", "Heuristic score component"),
        ("combined", "Combined score (after weighting)"),
        ("model_score", "Model adjustment term"),
        ("scoring_scope", "Scoring scope"),
        ("base_score", "Base / Sharpe-related term"),
        ("weight_penalty", "Concentration (weight) penalty"),
        ("volatility_penalty", "Volatility vs tolerance penalty"),
        ("total", "Universe match total (starter list)"),
    ):
        if key in sb and sb[key] is not None:
            lines.append(f"{label}: {sb[key]}.")
    return lines


def market_lines(expl: Dict[str, Any]) -> List[str]:
    m = expl.get("market") or expl.get("enrichment")
    if not isinstance(m, dict):
        return []
    lines: List[str] = []
    price = m.get("current_price") or (m.get("quote") or {}).get("price")
    if price is not None:
        lines.append(f"Market snapshot: last price ~${ _fmt_num(price) }.")
    if m.get("change_pct") is not None:
        lines.append(f"Session / recent change: {_fmt_num(m['change_pct'], 2)}%.")
    if m.get("trend_1m_pct") is not None:
        lines.append(f"Approx. ~30d price change: {_fmt_num(m['trend_1m_pct'], 2)}%.")
    if m.get("52w_high") is not None and m.get("52w_low") is not None:
        lines.append(
            f"52-week range in sample: ${_fmt_num(m['52w_low'])} – ${_fmt_num(m['52w_high'])}."
        )
    return lines


def risk_return_lines(expl: Dict[str, Any]) -> List[str]:
    rm = expl.get("risk_metrics")
    if not isinstance(rm, dict):
        return []
    lines: List[str] = []
    sh = rm.get("sharpe")
    vol = rm.get("volatility_annual")
    mdd = rm.get("max_drawdown")
    w = rm.get("weight")
    if sh is not None and "N/A" not in str(sh).upper():
        lines.append(
            f"Portfolio-level Sharpe (approx., from available history): {_fmt_num(sh)} - this is a portfolio proxy, not a symbol-level expected return forecast."
        )
    elif sh is not None:
        lines.append(str(sh))
    if vol is not None and "N/A" not in str(vol).upper():
        lines.append(
            f"Annualized volatility (portfolio proxy): {_fmt_num(vol)} — used with your risk tolerance to penalize outsized risk."
        )
    if mdd is not None and "N/A" not in str(mdd).upper():
        lines.append(f"Max drawdown (proxy): {_fmt_num(mdd)} — peak-to-trough decline in the sampled series.")
    if w is not None and "N/A" not in str(w).upper():
        try:
            wf = float(w)
            pct = wf * 100 if wf <= 1 else wf
        except (TypeError, ValueError):
            pct = w
        lines.append(
            f"This position's weight in the portfolio: {_fmt_num(pct, 2)}% "
            "(concentration affects the score)."
        )
    sb = expl.get("score_breakdown") if isinstance(expl.get("score_breakdown"), dict) else {}
    if sb and sb.get("type") == "holding":
        lines.append(
            "Holding ranking is generated from a portfolio-level base signal plus position-specific policy adjustments."
        )
    krc = expl.get("key_risk_contributors")
    if isinstance(krc, list) and krc:
        lines.append("Risk flags stored with this run: " + "; ".join(str(x) for x in krc[:6]) + ".")
    return lines


def sentiment_fallback_from_news(expl: Dict[str, Any]) -> Optional[str]:
    """If DB sentiment is empty, give a neutral data note from headlines."""
    news_block = expl.get("news_factors") if isinstance(expl.get("news_factors"), dict) else {}
    recent = news_block.get("recent_news") or []
    en = expl.get("enrichment") if isinstance(expl.get("enrichment"), dict) else {}
    if not recent and isinstance(en, dict):
        recent = en.get("recent_news") or []
    if not recent:
        return None
    providers = []
    for n in recent[:5]:
        sp = n.get("source_provider")
        if sp and sp not in providers:
            providers.append(sp)
    prov_str = ", ".join(providers) if providers else "aggregated feeds"
    titles = [str(n.get("title") or "").strip() for n in recent[:3] if n.get("title")]
    if not titles:
        return f"News-based context: {len(recent)} headline(s) in window ({prov_str}); no stored sentiment series for this symbol."
    return (
        f"News-based context ({prov_str}): recent headlines include “{titles[0][:100]}”"
        + (f" and {len(titles) - 1} more." if len(titles) > 1 else ".")
        + " Stored 7d sentiment scores are unavailable — use headlines as qualitative context only."
    )


def build_analyst_note(
    symbol: str,
    expl: Dict[str, Any],
    news_items: Optional[List[Dict[str, Any]]] = None,
) -> str:
    sec = expl.get("security") if isinstance(expl.get("security"), dict) else {}
    name = sec.get("full_name") or symbol
    sector = sec.get("sector") or "—"
    desc = (sec.get("description") or "").strip()
    parts: List[str] = [
        f"{name} ({symbol}) — {sector}.",
    ]
    if desc:
        parts.append(desc[:400] + ("…" if len(desc) > 400 else ""))
    mlines = market_lines(expl)
    if mlines:
        parts.append("Market inputs: " + mlines[0])
        if len(mlines) > 1:
            parts.append(mlines[1] + (f" {mlines[2]}" if len(mlines) > 2 else ""))
    news_items = news_items or []
    if not news_items:
        nf = expl.get("news_factors")
        if isinstance(nf, dict):
            news_items = nf.get("recent_news") or []
        en = expl.get("enrichment")
        if isinstance(en, dict) and not news_items:
            news_items = en.get("recent_news") or []
    if news_items:
        top = news_items[0]
        title = (top.get("title") or "")[:160]
        prov = top.get("source_provider") or "news"
        parts.append(f"Latest headline ({prov}): {title}.")
        if len(news_items) > 1:
            parts.append(f"+ {len(news_items) - 1} additional items in window from Benzinga / Finnhub / other configured providers.")
    parts.append(
        "This note summarizes data used for ranking under your settings — not a recommendation to transact."
    )
    return " ".join(p for p in parts if p)


def augment_explanation_for_detail(
    expl: Dict[str, Any],
    risk: Optional[Dict[str, Any]],
    finance_ctx: Optional[FinanceContext],
    symbol: str,
) -> None:
    """
    Mutates expl: adds why_selected_evidence, risk_return_narrative, refreshes why_selected,
    analyst_note_detail, sentiment_context.
    """
    evidence: List[Dict[str, str]] = []

    for line in preference_lines(risk):
        evidence.append({"source": "Your preferences", "detail": line})
    for line in finance_context_summary_lines(finance_ctx):
        evidence.append({"source": "Savings & goals (when enabled)", "detail": line})
    for line in score_breakdown_lines(expl):
        evidence.append({"source": "Score model", "detail": line})
    for line in market_lines(expl):
        evidence.append({"source": "Market data", "detail": line})

    expl["why_selected_evidence"] = evidence

    # Human-readable ordered bullets for UI (data-backed)
    expl["why_selected"] = [e["detail"] for e in evidence]

    expl["risk_return_narrative"] = risk_return_lines(expl)

    summ = expl.get("sentiment_summary")
    if not summ or not str(summ).strip():
        fallback = sentiment_fallback_from_news(expl)
        if fallback:
            expl["sentiment_summary"] = fallback
            expl["sentiment_context"] = "Headlines only (no sentiment DB series for this symbol)"
        else:
            expl["sentiment_summary"] = (
                "No 7-day sentiment series and no recent headlines were returned for this symbol "
                "(check API keys for news/market providers)."
            )
            expl["sentiment_context"] = "Unavailable"
    else:
        expl["sentiment_context"] = "7-day stored sentiment + news"

    expl["analyst_note_detail"] = build_analyst_note(symbol, expl)
    expl["analyst_note"] = expl["analyst_note_detail"]

    # Surface factor_contributions at the top level so the UI can render SHAP bars
    # without digging into score_breakdown (which varies by model type).
    sb = expl.get("score_breakdown")
    if isinstance(sb, dict):
        fc = sb.get("factor_contributions")
        if fc and isinstance(fc, dict):
            expl["factor_contributions"] = fc
        mv = sb.get("model_version")
        if mv:
            expl["model_version"] = mv
