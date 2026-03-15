"""Unit tests for AI explainer: prompt builder, post-process, router order."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_explainer import (
    NARRATIVE_BLOCKLIST,
    build_prompt,
    generate_narrative,
    _post_process,
)


def test_build_prompt_includes_disclaimer():
    payload = {"risk_metrics": {"sharpe": "0.5"}, "confidence": {"value": 0.8}}
    system, user = build_prompt(payload)
    assert "not financial advice" in system.lower()
    assert "informational purposes only" in system.lower()
    assert "80 words" in system.lower() or "80" in system
    assert "risk_metrics" in user or "sharpe" in user


def test_post_process_returns_none_for_empty():
    assert _post_process(None) is None
    assert _post_process("") is None
    assert _post_process("   ") is None


def test_post_process_rejects_blocklist_phrases():
    for phrase in NARRATIVE_BLOCKLIST:
        assert _post_process(f"Some text. {phrase.title()} more.") is None


def test_post_process_accepts_clean_text():
    clean = "This position has moderate risk-adjusted return based on Sharpe and weight."
    assert _post_process(clean) == clean


def test_post_process_truncates_long_text(monkeypatch):
    monkeypatch.setattr("app.services.ai_explainer.AI_EXPLAINER_MAX_NARRATIVE_CHARS", 20)
    out = _post_process("One two three four five six seven eight.")
    assert out is not None
    assert len(out) <= 20 + 10  # rsplit may add a word


@pytest.mark.asyncio
async def test_generate_narrative_returns_first_success(monkeypatch):
    """When first provider returns text, router returns it and provider name."""
    monkeypatch.setattr("app.services.ai_explainer._groq_configured", lambda: True)
    with patch("app.services.ai_explainer._groq_generate", new_callable=AsyncMock) as m:
        m.return_value = "Clean summary of risk."
        narrative, provider = await generate_narrative({"risk_metrics": {"sharpe": "0.5"}})
        assert m.called
        assert narrative == "Clean summary of risk."
        assert provider == "groq"
