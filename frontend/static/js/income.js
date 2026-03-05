/**
 * Income API helpers.
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
        if (opts.date_from) q.push('date_from=' + encodeURIComponent(opts.date_from));
        if (opts.date_to) q.push('date_to=' + encodeURIComponent(opts.date_to));
        if (opts.income_type) q.push('income_type=' + encodeURIComponent(opts.income_type));
        if (opts.page) q.push('page=' + encodeURIComponent(opts.page));
        if (opts.page_size) q.push('page_size=' + encodeURIComponent(opts.page_size));
        return q.length ? ('?' + q.join('&')) : '';
    }

    window.Income = {
        buildQuery: buildQuery,
        list: function(opts) {
            return request('/api/v1/income' + buildQuery(opts || {}));
        },
        create: function(payload) {
            return request('/api/v1/income', { method: 'POST', body: payload });
        },
        update: function(incomeId, payload) {
            return request('/api/v1/income/' + encodeURIComponent(incomeId), {
                method: 'PATCH',
                body: payload,
            });
        },
        remove: function(incomeId) {
            var headers = {};
            if (window.Auth && window.Auth.getAuthHeaders) {
                Object.assign(headers, window.Auth.getAuthHeaders());
            }
            return fetch(API + '/api/v1/income/' + encodeURIComponent(incomeId), {
                method: 'DELETE',
                headers: headers,
            }).then(function(r) {
                if (!r.ok) throw new Error(r.statusText || 'Delete failed');
            });
        },
        getSummary: function(groupBy, dateFrom, dateTo, convertTo) {
            var q = ['group_by=' + encodeURIComponent(groupBy || 'month')];
            if (dateFrom) q.push('date_from=' + encodeURIComponent(dateFrom));
            if (dateTo) q.push('date_to=' + encodeURIComponent(dateTo));
            if (convertTo) q.push('convert_to=' + encodeURIComponent(convertTo));
            return request('/api/v1/income/summary?' + q.join('&'));
        },
        getCashflow: function(dateFrom, dateTo, convertTo) {
            var q = [];
            if (dateFrom) q.push('date_from=' + encodeURIComponent(dateFrom));
            if (dateTo) q.push('date_to=' + encodeURIComponent(dateTo));
            if (convertTo) q.push('convert_to=' + encodeURIComponent(convertTo));
            return request('/api/v1/cashflow/summary' + (q.length ? '?' + q.join('&') : ''));
        }
    };
})();
