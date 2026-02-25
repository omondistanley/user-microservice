/**
 * Auth helpers — login and register using backend POST /login and POST /user.
 */
(function() {
    'use strict';
    var API = window.API_BASE || '';

    function getJson(r) {
        return r.json().catch(function() { return null; });
    }

    function getErrorDetail(r, data) {
        if (data && data.detail) {
            if (typeof data.detail === 'string') return data.detail;
            if (Array.isArray(data.detail)) return data.detail.map(function(d) { return d.msg || JSON.stringify(d); }).join(', ');
        }
        return r.statusText || 'Request failed';
    }

    var TOKEN_KEY = 'access_token';
    var REFRESH_TOKEN_KEY = 'refresh_token';
    var _refreshPromise = null;

    window.Auth = {
        getToken: function() {
            try {
                return localStorage.getItem(TOKEN_KEY) || null;
            } catch (e) {
                return null;
            }
        },
        getRefreshToken: function() {
            try {
                return localStorage.getItem(REFRESH_TOKEN_KEY) || null;
            } catch (e) {
                return null;
            }
        },
        getAuthHeaders: function() {
            var token = this.getToken();
            return token ? { Authorization: 'Bearer ' + token } : {};
        },
        isLoggedIn: function() {
            return !!this.getToken();
        },
        logout: function(sessionExpired) {
            try {
                localStorage.removeItem(TOKEN_KEY);
                localStorage.removeItem(REFRESH_TOKEN_KEY);
            } catch (e) {}
            window.location.href = sessionExpired ? '/login?session=expired' : '/login';
        },
        /** Call POST /token/refresh and update stored tokens. Returns new access_token or rejects. Only one refresh in flight at a time. */
        refreshAccessToken: function() {
            var ref = this.getRefreshToken();
            if (!ref) return Promise.reject(new Error('No refresh token'));
            if (_refreshPromise) return _refreshPromise;
            var self = this;
            _refreshPromise = fetch(API + '/token/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: ref })
            }).then(function(r) {
                return getJson(r).then(function(data) {
                    if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                    if (data && data.access_token) {
                        try {
                            localStorage.setItem(TOKEN_KEY, data.access_token);
                            if (data.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
                        } catch (e) {}
                        return data.access_token;
                    }
                    return Promise.reject(new Error('Refresh failed'));
                });
            }).finally(function() {
                _refreshPromise = null;
            });
            return _refreshPromise;
        },
        /** Fetch with auth; on 401 tries refresh once (shared) and retries. On 401 after retry (or no refresh), clears tokens and redirects to login. Returns response. */
        requestWithRefresh: function(url, options) {
            options = options || {};
            options.headers = Object.assign({}, this.getAuthHeaders(), options.headers);
            var self = this;
            function handle401(r) {
                if (r.status === 401) {
                    self.logout(true);
                    return r;
                }
                return r;
            }
            return fetch(url, options).then(function(r) {
                if (r.status === 401 && self.getRefreshToken()) {
                    return self.refreshAccessToken().then(function() {
                        options.headers = Object.assign({}, self.getAuthHeaders(), options.headers);
                        return fetch(url, options).then(handle401);
                    }).catch(function() {
                        self.logout(true);
                        return r;
                    });
                }
                return handle401(r);
            });
        },
        /** POST /login — form body: username (email), password. Returns { access_token, token_type, refresh_token? }. */
        login: function(email, password) {
            var body = new URLSearchParams({ username: email, password: password });
            return fetch(API + '/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body.toString()
            }).then(function(r) {
                return getJson(r).then(function(data) {
                    if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                    return data;
                });
            });
        },
        /** POST /user — JSON: email, first_name, last_name, password (min 8). Returns UserInfo. */
        register: function(email, first_name, last_name, password) {
            return fetch(API + '/user', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    first_name: first_name || '',
                    last_name: last_name || '',
                    password: password
                })
            }).then(function(r) {
                return getJson(r).then(function(data) {
                    if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                    return data;
                });
            });
        }
    };
})();
