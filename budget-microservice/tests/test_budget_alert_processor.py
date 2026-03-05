import os
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

# Ensure startup secret guard passes in test environments without .env.
os.environ.setdefault("SECRET_KEY", "test-secret")

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.jobs import budget_alert_processor as processor
from app.main import app

client = TestClient(app)


def test_openapi_includes_alert_evaluate_endpoint():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/v1/budgets/alerts/evaluate" in paths


def test_budget_alert_evaluation_is_deduplicated(monkeypatch):
    class FakeBudgetDataService:
        def __init__(self):
            self._seen = set()

        def list_active_budget_alert_targets(self, as_of_date, user_id=None):
            return [
                {
                    "budget_id": "7f322fec-4928-4645-b8c4-bdf0f314fda3",
                    "user_id": 1,
                    "category_code": 1,
                    "budget_amount": Decimal("100.00"),
                    "period_start": date(2026, 2, 1),
                    "period_end": date(2026, 2, 28),
                    "threshold_percent": Decimal("80.00"),
                    "channel": "in_app",
                }
            ]

        def get_spent_amount(self, user_id, category_code, period_start, period_end):
            return Decimal("95.00")

        def create_budget_alert_event(
            self,
            user_id,
            budget_id,
            period_start,
            period_end,
            threshold_percent,
            spent_amount,
            budget_amount,
            channel,
            sent_at=None,
        ):
            dedupe_key = (
                user_id,
                budget_id,
                period_start.isoformat(),
                period_end.isoformat(),
                str(threshold_percent),
                channel,
            )
            if dedupe_key in self._seen:
                return None
            self._seen.add(dedupe_key)
            return {
                "event_id": "adf4ef25-4950-497a-b180-a9d29389c374",
                "user_id": user_id,
                "budget_id": budget_id,
                "period_start": period_start,
                "period_end": period_end,
                "threshold_percent": threshold_percent,
                "spent_amount": spent_amount,
                "budget_amount": budget_amount,
                "channel": channel,
            }

    fake = FakeBudgetDataService()
    monkeypatch.setattr(processor, "_data_service", lambda: fake)
    monkeypatch.setattr(processor, "_notify_user_service", lambda event, request_id: None)

    first = processor.evaluate_budget_alerts(as_of_date=date(2026, 2, 27))
    second = processor.evaluate_budget_alerts(as_of_date=date(2026, 2, 27))

    assert first["processed_count"] == 1
    assert first["sent_count"] == 1
    assert first["failed_count"] == 0

    assert second["processed_count"] == 1
    assert second["sent_count"] == 0
    assert second["skipped_count"] == 1
    assert second["failed_count"] == 0
