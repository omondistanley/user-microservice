from datetime import date
from pathlib import Path

# Allow running without app installed as package.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.jobs import exchange_rate_sync as sync_job


def test_exchange_rate_sync_from_csv(tmp_path, monkeypatch):
    csv_file = tmp_path / "rates.csv"
    csv_file.write_text("currency,rate\nUSD,1.10\nKES,150.00\n", encoding="utf-8")

    captured = {}

    class FakeDataService:
        def upsert_exchange_rates(self, rate_date, source, rates, fetched_at=None):
            captured["rate_date"] = rate_date
            captured["source"] = source
            captured["count"] = len(rates)
            # EUR, USD, KES => 3x3 matrix
            assert len(rates) == 9
            return {"upserted_count": len(rates), "failed_count": 0}

    monkeypatch.setattr(sync_job, "_get_data_service", lambda: FakeDataService())

    result = sync_job.run_exchange_rate_sync(
        target_date=date(2026, 2, 27),
        csv_path=str(csv_file),
        job_id="test-sync-csv",
    )

    assert result["source"] == "CSV"
    assert result["rate_date"] == "2026-02-27"
    assert result["fetched_count"] == 9
    assert result["upserted_count"] == 9
    assert result["failed_count"] == 0
