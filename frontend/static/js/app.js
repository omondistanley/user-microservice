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

    window.EXPENSE_API_BASE = readMeta('expense-api-base');
    window.BUDGET_API_BASE = readMeta('budget-api-base');
    window.PLAID_FLOW = readMeta('plaid-flow') || 'hosted';
    // When gateway is configured, use it as the API base so auth/API calls go to the right origin
    var gatewayUrl = readMeta('gateway-public-url');
    window.API_BASE = gatewayUrl || '';
})();
