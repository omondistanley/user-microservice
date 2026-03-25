// @ts-nocheck
/**
 * Recurring expense API helpers.
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

    function buildQuery(opts) {
        opts = opts || {};
        var q = [];
        if (opts.active_only != null) q.push('active_only=' + encodeURIComponent(opts.active_only ? 'true' : 'false'));
        if (opts.page) q.push('page=' + encodeURIComponent(opts.page));
        if (opts.page_size) q.push('page_size=' + encodeURIComponent(opts.page_size));
        return q.length ? ('?' + q.join('&')) : '';
    }

    window.RecurringExpenses = {
        list: function(opts) {
            return request('/api/v1/recurring-expenses' + buildQuery(opts || {}));
        },
        create: function(payload) {
            return request('/api/v1/recurring-expenses', { method: 'POST', body: payload });
        },
        update: function(recurringId, payload) {
            return request('/api/v1/recurring-expenses/' + encodeURIComponent(recurringId), {
                method: 'PATCH',
                body: payload,
            });
        },
        remove: function(recurringId) {
            var headers = {};
            if (window.Auth && window.Auth.getAuthHeaders) {
                Object.assign(headers, window.Auth.getAuthHeaders());
            }
            return fetch(API + '/api/v1/recurring-expenses/' + encodeURIComponent(recurringId), {
                method: 'DELETE',
                headers: headers,
            }).then(function(r) {
                if (!r.ok) throw new Error(r.statusText || 'Delete failed');
            });
        },
        runNow: function(recurringId) {
            return request('/api/v1/recurring-expenses/' + encodeURIComponent(recurringId) + '/run', {
                method: 'POST'
            });
        }
    };
})();
