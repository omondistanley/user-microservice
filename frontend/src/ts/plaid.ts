// @ts-nocheck
/**
 * Plaid: link token, exchange, list/delete items, sync.
 * Uses EXPENSE_API_BASE and Auth (same as expenses.js).
 */
(function() {
    'use strict';
    var API = window.EXPENSE_API_BASE !== undefined && window.EXPENSE_API_BASE !== ''
        ? window.EXPENSE_API_BASE
        : (window.API_BASE || '');

    function request(path, options) {
        options = options || {};
        options.headers = options.headers || {};
        if (window.Auth && window.Auth.getAuthHeaders) {
            Object.assign(options.headers, window.Auth.getAuthHeaders());
        }
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }
        var doFetch = (window.Auth && window.Auth.requestWithRefresh)
            ? function() { return window.Auth.requestWithRefresh(API + path, options); }
            : function() { return fetch(API + path, options); };
        return doFetch().then(function(r) {
            if (!r.ok) throw new Error(r.statusText || 'Request failed');
            return r.json().catch(function() { return null; });
        });
    }

    window.PlaidApi = {
        getLinkToken: function() {
            return request('/api/v1/plaid/link-token', { method: 'POST' });
        },
        getHostedLink: function(completionRedirectUri) {
            return request('/api/v1/plaid/link-hosted', {
                method: 'POST',
                body: completionRedirectUri ? { completion_redirect_uri: completionRedirectUri } : undefined,
            });
        },
        linkTokenGet: function(linkToken) {
            return request('/api/v1/plaid/link-token/get', {
                method: 'POST',
                body: { link_token: linkToken },
            });
        },
        exchangeItem: function(publicToken) {
            return request('/api/v1/plaid/item', {
                method: 'POST',
                body: { public_token: publicToken },
            });
        },
        getItems: function() {
            return request('/api/v1/plaid/items');
        },
        /** Per-account rows from Plaid /accounts/get (names, masks, types; not live balances). */
        getAccounts: function() {
            return request('/api/v1/plaid/accounts');
        },
        deleteItem: function(itemId) {
            var headers = {};
            if (window.Auth && window.Auth.getAuthHeaders) {
                Object.assign(headers, window.Auth.getAuthHeaders());
            }
            var doFetch = (window.Auth && window.Auth.requestWithRefresh)
                ? function() { return window.Auth.requestWithRefresh(API + '/api/v1/plaid/items/' + encodeURIComponent(itemId), { method: 'DELETE', headers: headers }); }
                : function() { return fetch(API + '/api/v1/plaid/items/' + encodeURIComponent(itemId), { method: 'DELETE', headers: headers }); };
            return doFetch().then(function(r) {
                if (!r.ok) throw new Error(r.statusText || 'Request failed');
                return r.json().catch(function() { return {}; });
            });
        },
        sync: function(dateFrom, dateTo) {
            var body = {};
            if (dateFrom) body.date_from = dateFrom;
            if (dateTo) body.date_to = dateTo;
            return request('/api/v1/plaid/sync', {
                method: 'POST',
                body: Object.keys(body).length ? body : undefined,
            });
        },
    };
})();
