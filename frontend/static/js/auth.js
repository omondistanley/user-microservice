"use strict";
(function() {
  "use strict";
  const API = window.API_BASE || "";
  function getJson(r) {
    return r.json().catch(function() {
      return null;
    });
  }
  function getErrorDetail(r, data) {
    if (data && data.detail) {
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail))
        return data.detail.map(function(d) {
          return d.msg || JSON.stringify(d);
        }).join(", ");
    }
    return r.statusText || "Request failed";
  }
  const TOKEN_KEY = "access_token";
  const REFRESH_TOKEN_KEY = "refresh_token";
  let _refreshPromise = null;
  window.Auth = {
    getToken: function() {
      try {
        return localStorage.getItem(TOKEN_KEY) || null;
      } catch {
        return null;
      }
    },
    getAccessToken: function() {
      return this.getToken();
    },
    getRefreshToken: function() {
      try {
        return localStorage.getItem(REFRESH_TOKEN_KEY) || null;
      } catch {
        return null;
      }
    },
    getAuthHeaders: function() {
      const token = this.getToken();
      return token ? { Authorization: "Bearer " + token } : {};
    },
    isLoggedIn: function() {
      return !!this.getToken();
    },
    logout: function(sessionExpired) {
      try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
      } catch {
      }
      window.location.href = sessionExpired ? "/login?session=expired" : "/login";
    },
    refreshAccessToken: function() {
      const ref = this.getRefreshToken();
      if (!ref) return Promise.reject(new Error("No refresh token"));
      if (_refreshPromise) return _refreshPromise;
      _refreshPromise = fetch(API + "/token/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: ref })
      }).then(function(r) {
        return getJson(r).then(function(data) {
          if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
          if (data && data.access_token) {
            try {
              localStorage.setItem(TOKEN_KEY, String(data.access_token));
              if (data.refresh_token)
                localStorage.setItem(REFRESH_TOKEN_KEY, String(data.refresh_token));
            } catch {
            }
            return String(data.access_token);
          }
          return Promise.reject(new Error("Refresh failed"));
        });
      }).finally(function() {
        _refreshPromise = null;
      });
      return _refreshPromise;
    },
    requestWithRefresh: function(url, options) {
      options = options || {};
      options.headers = Object.assign({}, this.getAuthHeaders(), options.headers);
      const self = this;
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
    login: function(email, password) {
      const base = typeof window !== "undefined" && window.API_BASE !== void 0 ? window.API_BASE : API;
      const body = new URLSearchParams({ username: email, password });
      return fetch((base || "") + "/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString()
      }).then(function(r) {
        return getJson(r).then(function(data) {
          if (!r.ok) return Promise.reject(new Error(getErrorDetail(r, data)));
          return data;
        });
      });
    },
    fetchGatewayJson: function(path, options) {
      options = options || {};
      const base = typeof window !== "undefined" && window.API_BASE ? window.API_BASE : API;
      const url = (base || "") + path;
      options.headers = Object.assign({}, this.getAuthHeaders(), options.headers || {});
      if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.body);
      }
      const self = this;
      const run = self.requestWithRefresh ? function() {
        return self.requestWithRefresh(url, options);
      } : function() {
        return fetch(url, options);
      };
      return run().then(function(r) {
        if (!r.ok) {
          return getJson(r).then(function(data) {
            return Promise.reject(new Error(getErrorDetail(r, data)));
          });
        }
        if (r.status === 204) return null;
        return getJson(r);
      });
    },
    register: function(email, first_name, last_name, password) {
      const base = typeof window !== "undefined" && window.API_BASE !== void 0 ? window.API_BASE : API;
      return fetch((base || "") + "/user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          first_name: first_name || "",
          last_name: last_name || "",
          password
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
