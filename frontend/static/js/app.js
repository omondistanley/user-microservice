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
    window.API_BASE = ''; // same origin: user-microservice
})();
