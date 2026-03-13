from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.net_worth as net_worth_router  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


@pytest.mark.asyncio
async def test_net_worth_summary_aggregates_components(monkeypatch):
  async def fake_fetch_expense(request):
      return {
          "assets": {"cash": "1000.00", "income_window_total": "9999.99"},
          "liabilities": {"spending_obligation": "250.00"},
          "metadata": {"as_of_date": "2026-03-13"},
      }

  async def fake_fetch_investments(request):
      return {
          "total_market_value": "5000.00",
          "total_cost_basis": "4000.00",
          "unrealized_pl": "1000.00",
          "metadata": {"valuation_source": "test"},
      }

  monkeypatch.setattr(net_worth_router, "_fetch_expense_components", fake_fetch_expense)
  monkeypatch.setattr(net_worth_router, "_fetch_investments_portfolio", fake_fetch_investments)

  r = client.get("/api/v1/net-worth/summary")
  assert r.status_code == 200
  body = r.json()

  # Net worth = assets (cash + investments) - liabilities
  assert Decimal(str(body["assets"]["cash"])) == Decimal("1000.00")
  assert Decimal(str(body["assets"]["investments"])) == Decimal("5000.00")
  assert Decimal(str(body["assets_total"])) == Decimal("6000.00")
  assert Decimal(str(body["liabilities"]["debt"])) == Decimal("250.00")
  assert Decimal(str(body["liabilities_total"])) == Decimal("250.00")
  assert Decimal(str(body["net_worth"])) == Decimal("5750.00")


@pytest.mark.asyncio
async def test_net_worth_summary_ignores_cashflow_fields(monkeypatch):
  async def fake_fetch_expense(request):
      return {
          "assets": {"cash": "1000.00", "income_window_total": "999999.00"},
          "liabilities": {"spending_obligation": "0"},
      }

  async def fake_fetch_investments(request):
      return None

  monkeypatch.setattr(net_worth_router, "_fetch_expense_components", fake_fetch_expense)
  monkeypatch.setattr(net_worth_router, "_fetch_investments_portfolio", fake_fetch_investments)

  r = client.get("/api/v1/net-worth/summary")
  assert r.status_code == 200
  body = r.json()

  # income_window_total must not affect assets_total or net_worth
  assert Decimal(str(body["assets"]["cash"])) == Decimal("1000.00")
  assert Decimal(str(body["assets"]["investments"])) == Decimal("0")
  assert Decimal(str(body["assets_total"])) == Decimal("1000.00")
  assert Decimal(str(body["net_worth"])) == Decimal("1000.00")

