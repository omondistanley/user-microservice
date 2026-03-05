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


def test_categories_require_auth():
    r = client.get("/api/v1/categories")
    assert r.status_code == 401


def test_expenses_require_auth():
    r = client.get("/api/v1/expenses")
    assert r.status_code == 401
    r = client.post("/api/v1/expenses", json={"amount": 10, "date": "2025-01-01", "category": "Food"})
    assert r.status_code == 401


def test_summary_requires_auth():
    r = client.get("/api/v1/expenses/summary?group_by=category")
    assert r.status_code == 401


def test_income_requires_auth():
    r = client.get("/api/v1/income")
    assert r.status_code == 401
    r = client.post(
        "/api/v1/income",
        json={"amount": 1000, "date": "2025-01-01", "income_type": "salary"},
    )
    assert r.status_code == 401


def test_recurring_requires_auth():
    r = client.get("/api/v1/recurring-expenses")
    assert r.status_code == 401
    r = client.post(
        "/api/v1/recurring-expenses",
        json={
            "amount": 9.99,
            "category": "Food",
            "recurrence_rule": "monthly",
            "next_due_date": "2025-01-01",
        },
    )
    assert r.status_code == 401
