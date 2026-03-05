from datetime import date

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.jobs import recurring_due_processor as processor
from app.services.expense_data_service import ExpenseDataService


class _FakeExpenseDataService(ExpenseDataService):
    def __init__(self, result):
        self._result = result

    def process_due_recurring_batch(self, as_of_date: date, limit: int = 500):  # type: ignore[override]
        return self._result


def test_run_recurring_due_processor_success(monkeypatch):
    fake = _FakeExpenseDataService(
        {
            "as_of_date": "2026-02-27",
            "candidate_count": 2,
            "processed_count": 2,
            "skipped_count": 0,
            "failed_count": 0,
            "failures": [],
        }
    )
    monkeypatch.setattr(
        processor.ServiceFactory,
        "get_service",
        lambda service_name: fake if service_name == "ExpenseDataService" else None,
    )
    code = processor.run_recurring_due_processor(
        as_of_date=date(2026, 2, 27),
        limit=100,
        job_id="test-job-success",
    )
    assert code == 0


def test_run_recurring_due_processor_failure(monkeypatch):
    fake = _FakeExpenseDataService(
        {
            "as_of_date": "2026-02-27",
            "candidate_count": 2,
            "processed_count": 1,
            "skipped_count": 0,
            "failed_count": 1,
            "failures": [{"recurring_id": "a9f9c6e7-6322-48ce-9f34-b3de4ea2d4b3", "error": "boom"}],
        }
    )
    monkeypatch.setattr(
        processor.ServiceFactory,
        "get_service",
        lambda service_name: fake if service_name == "ExpenseDataService" else None,
    )
    code = processor.run_recurring_due_processor(
        as_of_date=date(2026, 2, 27),
        limit=100,
        job_id="test-job-failure",
    )
    assert code == 1
