(function() {
    'use strict';

    var API = window.API_BASE || '';

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

    window.Settings = {
        get: function() {
            return request('/api/v1/settings');
        },
        updateCurrency: function(currency) {
            return request('/api/v1/settings', {
                method: 'PATCH',
                body: { default_currency: String(currency || '').toUpperCase() }
            });
        }
    };
})();
