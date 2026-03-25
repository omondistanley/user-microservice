/**
 * Auth helpers — login and register using backend POST /login and POST /user.
 * Source of truth for auth.js (build with `npm run build:js`).
 */
(function () {
    'use strict';
    const API = window.API_BASE || '';

    function getJson(r: Response): Promise<Record<string, unknown> | null> {
        return r.json().catch(function () {
            return null;
        }) as Promise<Record<string, unknown> | null>;
    }

    function getErrorDetail(r: Response, data: Record<string, unknown> | null): string {
        if (data && data.detail) {
            if (typeof data.detail === 'string') return data.detail;
            if (Array.isArray(data.detail))
                return data.detail
                    .map(function (d: { msg?: string }) {
                        return d.msg || JSON.stringify(d);
                    })
                    .join(', ');
        }
        return r.statusText || 'Request failed';
    }

    const TOKEN_KEY = 'access_token';
    const REFRESH_TOKEN_KEY = 'refresh_token';
    let _refreshPromise: Promise<string> | null = null;

    window.Auth = {
        getToken: function () {
            try {
                return localStorage.getItem(TOKEN_KEY) || null;
            } catch {
                return null;
            }
        },
        getAccessToken: function () {
            return this.getToken();
        },
        getRefreshToken: function () {
            try {
                return localStorage.getItem(REFRESH_TOKEN_KEY) || null;
            } catch {
                return null;
            }
        },
        getAuthHeaders: function (): Record<string, string> {
            const token = this.getToken();
            return token ? { Authorization: 'Bearer ' + token } : ({} as Record<string, string>);
        },
        isLoggedIn: function () {
            return !!this.getToken();
        },
        logout: function (sessionExpired?: boolean): void {
            try {
                localStorage.removeItem(TOKEN_KEY);
                localStorage.removeItem(REFRESH_TOKEN_KEY);
            } catch {
                /* ignore */
            }
            window.location.href = sessionExpired ? '/login?session=expired' : '/login';
        },
        refreshAccessToken: function () {
            const ref = this.getRefreshToken();
            if (!ref) return Promise.reject(new Error('No refresh token'));
            if (_refreshPromise) return _refreshPromise;
            _refreshPromise = fetch(API + '/token/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: ref }),
            })
                .then(function (r) {
                    return getJson(r).then(function (data) {
                        if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                        if (data && data.access_token) {
                            try {
                                localStorage.setItem(TOKEN_KEY, String(data.access_token));
                                if (data.refresh_token)
                                    localStorage.setItem(REFRESH_TOKEN_KEY, String(data.refresh_token));
                            } catch {
                                /* ignore */
                            }
                            return String(data.access_token);
                        }
                        return Promise.reject(new Error('Refresh failed'));
                    });
                })
                .finally(function () {
                    _refreshPromise = null;
                });
            return _refreshPromise;
        },
        requestWithRefresh: function (url: string, options?: RequestInit) {
            options = options || {};
            options.headers = Object.assign({}, this.getAuthHeaders(), options.headers);
            const self = this;
            function handle401(r: Response) {
                if (r.status === 401) {
                    self.logout(true);
                    return r;
                }
                return r;
            }
            return fetch(url, options).then(function (r) {
                if (r.status === 401 && self.getRefreshToken()) {
                    return self.refreshAccessToken().then(function () {
                        options!.headers = Object.assign({}, self.getAuthHeaders(), options!.headers);
                        return fetch(url, options!).then(handle401);
                    }).catch(function () {
                        self.logout(true);
                        return r;
                    });
                }
                return handle401(r);
            });
        },
        login: function (email: string, password: string) {
            const base =
                typeof window !== 'undefined' && window.API_BASE !== undefined ? window.API_BASE : API;
            const body = new URLSearchParams({ username: email, password: password });
            return fetch((base || '') + '/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body.toString(),
            }).then(function (r) {
                return getJson(r).then(function (data) {
                    if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                    return data as Record<string, unknown>;
                });
            });
        },
        fetchGatewayJson: function (path: string, options?: RequestInit) {
            options = options || {};
            const base = typeof window !== 'undefined' && window.API_BASE ? window.API_BASE : API;
            const url = (base || '') + path;
            options.headers = Object.assign({}, this.getAuthHeaders(), options.headers || {});
            if (
                options.body &&
                typeof options.body === 'object' &&
                !(options.body instanceof FormData)
            ) {
                (options.headers as Record<string, string>)['Content-Type'] = 'application/json';
                options.body = JSON.stringify(options.body);
            }
            const self = this;
            const run = self.requestWithRefresh
                ? function () {
                      return self.requestWithRefresh(url, options);
                  }
                : function () {
                      return fetch(url, options);
                  };
            return run().then(function (r) {
                if (!r.ok) {
                    return getJson(r).then(function (data) {
                        return Promise.reject(new Error(getErrorDetail(r, data)));
                    });
                }
                if (r.status === 204) return null;
                return getJson(r);
            });
        },
        register: function (email: string, first_name: string, last_name: string, password: string) {
            const base =
                typeof window !== 'undefined' && window.API_BASE !== undefined ? window.API_BASE : API;
            return fetch((base || '') + '/user', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    first_name: first_name || '',
                    last_name: last_name || '',
                    password: password,
                }),
            }).then(function (r) {
                return getJson(r).then(function (data) {
                    if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
                    return data as Record<string, unknown>;
                });
            });
        },
    };
})();
