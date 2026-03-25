#!/bin/bash
# Fly release_command: create DBs (if missing) and run migrations.
# Only runs migrations that are not yet recorded in public.schema_migrations per DB.
# Uses DB_HOST, DB_PORT, DB_USER, DB_PASSWORD from Fly secrets.
TRACKED="/opt/run_migration_tracked.py"

echo "release: creating databases if missing..."
python3 /opt/create_dbs.py

echo "release: running user migrations..."
export DB_NAME=users_db
for f in /opt/expense_tracker/user-microservice/migrations/create_user_table.sql \
         /opt/expense_tracker/user-microservice/migrations/002_refresh_token.sql \
         /opt/expense_tracker/user-microservice/migrations/003_password_reset_token.sql \
         /opt/expense_tracker/user-microservice/migrations/004_email_verification.sql \
         /opt/expense_tracker/user-microservice/migrations/005_oauth_provider.sql \
         /opt/expense_tracker/user-microservice/migrations/006_security_audit_and_refresh_hardening.sql \
         /opt/expense_tracker/user-microservice/migrations/007_user_notification.sql \
         /opt/expense_tracker/user-microservice/migrations/008_user_settings.sql \
         /opt/expense_tracker/user-microservice/migrations/009_household.sql \
         /opt/expense_tracker/user-microservice/migrations/010_household_member.sql \
         /opt/expense_tracker/user-microservice/migrations/011_active_household.sql \
         /opt/expense_tracker/user-microservice/migrations/012_report_saved_view.sql \
         /opt/expense_tracker/user-microservice/migrations/013_user_session.sql \
         /opt/expense_tracker/user-microservice/migrations/014_retention_policy.sql \
         /opt/expense_tracker/user-microservice/migrations/015_webhook_events.sql \
         /opt/expense_tracker/user-microservice/migrations/016_digest_config.sql \
         /opt/expense_tracker/user-microservice/migrations/017_webhook_event_lifecycle.sql \
         /opt/expense_tracker/user-microservice/migrations/018_calendar_subscription_token.sql \
         /opt/expense_tracker/user-microservice/migrations/019_net_worth_manual.sql \
         /opt/expense_tracker/user-microservice/migrations/020_calendar_oauth_connection.sql \
         /opt/expense_tracker/user-microservice/migrations/020_lifecycle_events.sql \
         /opt/expense_tracker/user-microservice/migrations/021_retention_policy_investments_expense.sql; do
  [ -f "$f" ] && python3 "$TRACKED" "$f" || echo "warning: migration failed: $f"
done

echo "release: running expense migrations..."
export DB_NAME=expenses_db
for f in /opt/expense/migrations/001_schema.sql \
         /opt/expense/migrations/002_receipt_file_bytes.sql \
         /opt/expense/migrations/003_idempotency.sql \
         /opt/expense/migrations/004_plaid.sql \
         /opt/expense/migrations/005_income_and_recurring.sql \
         /opt/expense/migrations/006_tags.sql \
         /opt/expense/migrations/007_exchange_rate.sql \
         /opt/expense/migrations/008_teller.sql \
         /opt/expense/migrations/009_household_scope.sql \
         /opt/expense/migrations/010_expense_import.sql \
         /opt/expense/migrations/011_savings_goals.sql \
         /opt/expense/migrations/012_anomaly_feedback.sql \
         /opt/expense/migrations/013_receipt_ocr.sql \
         /opt/expense/migrations/014_plaid_provider.sql \
         /opt/expense/migrations/015_apple_wallet.sql \
         /opt/expense/migrations/016_user_categorization_rule.sql \
         /opt/expense/migrations/017_round_up_goal.sql \
         /opt/expense/migrations/018_no_income_notification_dedup.sql \
         /opt/expense/migrations/019_user_alert_preferences.sql \
         /opt/expense/migrations/020_expense_match.sql \
         /opt/expense/migrations/021_receipt_expense_nullable.sql \
         /opt/expense/migrations/022_plaid_link_token.sql \
         /opt/expense/migrations/023_income_apple_wallet_idempotency.sql \
         /opt/expense/migrations/024_apple_wallet_sync_state.sql \
         /opt/expense/migrations/025_classifier_corrections.sql \
         /opt/expense/migrations/026_gmail_oauth.sql \
         /opt/expense/migrations/027_global_idempotency.sql \
         /opt/expense/migrations/028_gmail_google_account_email.sql \
         /opt/expense/migrations/029_user_irregular_expenses.sql \
         /opt/expense/migrations/030_income_ira_contribution.sql; do
  [ -f "$f" ] && python3 "$TRACKED" "$f" || echo "warning: migration failed: $f"
done

echo "release: running budget migrations..."
export DB_NAME=budgets_db
for f in /opt/budget/migrations/001_schema.sql \
         /opt/budget/migrations/002_budget_alerts.sql \
         /opt/budget/migrations/003_spend_pace_event.sql \
         /opt/budget/migrations/003_household_scope.sql \
         /opt/budget/migrations/004_recurring_budget.sql; do
  [ -f "$f" ] && python3 "$TRACKED" "$f" || echo "warning: migration failed: $f"
done

echo "release: running investment migrations..."
export DB_NAME=investments_db
for f in /opt/investment/migrations/001_schema.sql \
         /opt/investment/migrations/002_market_intelligence.sql \
         /opt/investment/migrations/003_recommendations_preferences.sql \
         /opt/investment/migrations/004_security_universe.sql \
         /opt/investment/migrations/005_sector_cache.sql \
         /opt/investment/migrations/006_etf_holdings.sql \
         /opt/investment/migrations/008_tax_lots.sql \
         /opt/investment/migrations/009_scenarios.sql \
         /opt/investment/migrations/010_fundamental_snapshot.sql \
         /opt/investment/migrations/011_sentiment_snapshot.sql \
         /opt/investment/migrations/012_alpaca_connection.sql \
         /opt/investment/migrations/013_risk_profile_use_finance_data.sql \
         /opt/investment/migrations/014_recommendation_run_portfolio_snapshot.sql \
         /opt/investment/migrations/015_portfolio_rebalance_sessions.sql \
         /opt/investment/migrations/016_holdings_account_type_role_label.sql \
         /opt/investment/migrations/017_portfolio_health_snapshot.sql \
         /opt/investment/migrations/018_recommendation_digests.sql \
         /opt/investment/migrations/019_watchlist.sql \
         /opt/investment/migrations/020_nudge_log.sql \
         /opt/investment/migrations/021_etf_constituents.sql \
         /opt/investment/migrations/022_dividend_calendar.sql \
         /opt/investment/migrations/029_recommendation_run_artifacts.sql; do
  [ -f "$f" ] && python3 "$TRACKED" "$f" || echo "warning: migration failed: $f"
done

echo "release: done"
