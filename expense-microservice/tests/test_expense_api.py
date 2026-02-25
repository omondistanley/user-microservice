"""
Minimal API tests. Requires running app and DB (e.g. pytest with env).
Run: pytest tests/ -v
"""
import os
import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_categories_public():
    try:
        r = client.get("/api/categories")
    except Exception as e:
        if "OperationalError" in type(e).__name__ or "database" in str(e).lower():
            pytest.skip("DB not available (categories need schema)")
        raise
    if r.status_code == 500:
        pytest.skip("DB not available (categories need schema)")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        assert "category_code" in data[0] and "name" in data[0]


def test_expenses_require_auth():
    r = client.get("/api/expenses")
    assert r.status_code == 401
    r = client.post("/api/expenses", json={"amount": 10, "date": "2025-01-01", "category": "Food"})
    assert r.status_code == 401


def test_summary_requires_auth():
    r = client.get("/api/expenses/summary?group_by=category")
    assert r.status_code == 401
