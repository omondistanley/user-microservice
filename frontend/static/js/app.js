/**
 * Expense Tracker — shared frontend config and helpers.
 * API is served by user-microservice; same origin when served from that app.
 */
(function() {
    'use strict';
    function readMeta(name) {
        var meta = document.querySelector('meta[name="' + name + '"]');
        return meta ? (meta.getAttribute('content') || '') : '';
    }

    // EXPENSE_API_BASE / BUDGET_API_BASE: direct microservice URLs for local dev only. Production uses same-origin gateway.
    window.EXPENSE_API_BASE = readMeta('expense-api-base');
    window.BUDGET_API_BASE = readMeta('budget-api-base');
    window.PLAID_FLOW = readMeta('plaid-flow') || 'hosted';
    // Gateway URL: use for user auth, investments, budgets (when unset), and any path not covered by service-specific bases.
    var gatewayUrl = readMeta('gateway-public-url');
    window.API_BASE = gatewayUrl || '';
})();
