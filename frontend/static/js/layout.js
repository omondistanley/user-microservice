"use strict";
(function() {
  "use strict";
  var path = window.location.pathname;
  var hash = window.location.hash;
  if (hash && hash.indexOf("access_token=") !== -1) {
    var params = new URLSearchParams(hash.slice(1));
    var accessToken = params.get("access_token");
    var refreshToken = params.get("refresh_token");
    if (accessToken) {
      try {
        localStorage.setItem("access_token", accessToken);
        if (refreshToken) {
          localStorage.setItem("refresh_token", refreshToken);
        }
      } catch (e) {
      }
      window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
    }
  }
  function applyAuthState() {
    var guest = document.querySelectorAll(".nav-guest");
    var authEls = document.querySelectorAll(".nav-auth");
    var logoutLink = document.getElementById("nav-logout-link");
    if (!window.Auth || !window.Auth.isLoggedIn) {
      return;
    }
    if (window.Auth.isLoggedIn()) {
      if (guest.length) {
        guest.forEach(function(el) {
          el.style.display = "none";
        });
      }
      if (authEls.length) {
        authEls.forEach(function(el) {
          el.style.display = "";
        });
      }
      if (logoutLink) {
        logoutLink.onclick = function(e) {
          e.preventDefault();
          window.Auth.logout();
        };
      }
      var publicPaths = ["/", "/landing", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/verify-email/pending", "/welcome"];
      var isPublic = publicPaths.indexOf(path) !== -1;
      if (!isPublic && window.Notifications && window.Notifications.start) {
        window.Notifications.start();
      }
      if (!isPublic) {
        initHouseholdSwitcher();
        maybeAutoConnectCalendar();
      }
    } else {
      if (guest.length) {
        guest.forEach(function(el) {
          el.style.display = "";
        });
      }
      if (authEls.length) {
        authEls.forEach(function(el) {
          el.style.display = "none";
        });
      }
    }
  }
  function maybeAutoConnectCalendar() {
    var keyDone = "calendar_oauth_autoconnect_done_v1";
    var keySkip = "calendar_oauth_autoconnect_skip_v1";
    var currentPath = window.location.pathname || "";
    if (currentPath.indexOf("/api/") === 0 || currentPath === "/login" || currentPath === "/register") return;
    try {
      if (localStorage.getItem(keyDone) === "1" || localStorage.getItem(keySkip) === "1") return;
    } catch (e) {
      return;
    }
    if (!window.Auth || !window.Auth.fetchGatewayJson) return;
    window.Auth.fetchGatewayJson("/api/v1/calendar/status").then(function(status) {
      if (status && status.connected) {
        try {
          localStorage.setItem(keyDone, "1");
        } catch (e) {
        }
        return;
      }
      if (!window.confirm("Connect your calendar now to automatically sync bill reminders and due dates?")) {
        try {
          localStorage.setItem(keySkip, "1");
        } catch (e) {
        }
        return;
      }
      return window.Auth.fetchGatewayJson("/api/v1/calendar/oauth/authorize?provider=google&json=1").then(function(data) {
        if (data && data.authorization_url) {
          window.location.href = data.authorization_url;
        }
      });
    }).catch(function() {
      try {
        localStorage.setItem(keySkip, "1");
      } catch (e) {
      }
    });
  }
  function initHouseholdSwitcher() {
    var wrap = document.getElementById("household-switcher-wrap");
    var sel = document.getElementById("household-switcher");
    if (!wrap || !sel) return;
    var API = window.API_BASE || "";
    var headers = window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
    Promise.all([
      fetch(API + "/api/v1/settings", { headers }).then(function(r) {
        return r.ok ? r.json() : null;
      }),
      fetch(API + "/api/v1/households", { headers }).then(function(r) {
        return r.ok ? r.json() : null;
      })
    ]).then(function(results) {
      var settings = results[0];
      var households = results[1];
      var activeId = settings && settings.active_household_id ? settings.active_household_id : "";
      sel.innerHTML = '<option value="">Personal</option>';
      if (households && households.items && households.items.length) {
        households.items.forEach(function(h) {
          var opt = document.createElement("option");
          opt.value = h.household_id || "";
          opt.textContent = h.name || "Household";
          sel.appendChild(opt);
        });
      }
      sel.value = activeId;
      wrap.style.display = "block";
    }).catch(function() {
    });
    sel.addEventListener("change", function() {
      var val = sel.value;
      var body = JSON.stringify({ household_id: val || null });
      fetch(API + "/api/v1/settings/active-household", {
        method: "PATCH",
        headers: Object.assign({ "Content-Type": "application/json" }, headers),
        body
      }).then(function(r) {
        if (r.ok) window.location.reload();
      });
    });
  }
  var protectedPaths = [
    "/dashboard",
    "/transactions",
    "/analytics",
    "/expenses",
    "/expenses/add",
    "/expenses/import",
    "/income",
    "/income/add",
    "/recurring",
    "/link-bank",
    "/budgets",
    "/budgets/add",
    "/reports",
    "/insights",
    "/goals",
    "/goals/add",
    "/investments",
    "/investments/add",
    "/recommendations",
    "/net-worth",
    "/notifications",
    "/household",
    "/sessions",
    "/profile",
    "/settings",
    "/saved-views"
  ];
  var isProtected = protectedPaths.indexOf(path) !== -1 || path.startsWith("/expenses/") || path.startsWith("/budgets/") || path.startsWith("/goals/") || path.startsWith("/investments/") || path.startsWith("/settings/");
  if (isProtected && window.Auth && !window.Auth.isLoggedIn()) {
    window.location.href = "/login?next=" + encodeURIComponent(path);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyAuthState);
  } else {
    applyAuthState();
  }
  function initAppShell() {
    var topbarDate = document.getElementById("topbar-date");
    if (topbarDate) {
      var d = /* @__PURE__ */ new Date();
      topbarDate.textContent = d.toLocaleDateString(void 0, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
    }
    var greeting = document.getElementById("topbar-greeting");
    if (greeting && window.Auth && window.Auth.isLoggedIn()) {
      var hour = (/* @__PURE__ */ new Date()).getHours();
      greeting.textContent = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    }
    var syncEl = document.getElementById("shell-sync-status");
    if (syncEl && window.Auth && window.Auth.fetchGatewayJson) {
      window.Auth.fetchGatewayJson("/api/v1/sync-status").then(function(s) {
        if (!s) return;
        var parts = [];
        if (s.bank_linked) {
          if (s.last_bank_connection_update_at) {
            parts.push("Bank linked \xB7 updated " + new Date(s.last_bank_connection_update_at).toLocaleString());
          } else {
            parts.push("Bank linked");
          }
        } else {
          parts.push("No bank connection");
        }
        if (s.apple_wallet_last_sync_at) {
          parts.push("Apple Wallet sync " + new Date(s.apple_wallet_last_sync_at).toLocaleString());
        }
        syncEl.textContent = parts.join(" \xB7 ");
      }).catch(function() {
        syncEl.textContent = "";
      });
    }
    var sidebarAvatar = document.getElementById("sidebar-avatar");
    var sidebarName = document.getElementById("sidebar-user-name");
    var sidebarEmail = document.getElementById("sidebar-user-email");
    if (window.Auth && window.Auth.getToken && sidebarName) {
      try {
        var token = window.Auth.getToken();
        if (token) {
          var payload = JSON.parse(atob(token.split(".")[1] || "{}"));
          if (payload.email) sidebarEmail && (sidebarEmail.textContent = payload.email);
          if (payload.name) sidebarName.textContent = payload.name;
          else if (payload.email) sidebarName.textContent = payload.email.split("@")[0] || "User";
          if (sidebarAvatar && (payload.name || payload.email)) sidebarAvatar.textContent = (payload.name || payload.email).charAt(0).toUpperCase();
        }
      } catch (e) {
      }
    }
  }
  if (document.body.classList.contains("app-shell-page")) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initAppShell);
    } else {
      initAppShell();
    }
  }
  var filtersToggle = document.getElementById("navbar-filters-toggle");
  var filtersPanel = document.getElementById("navbar-filters-panel");
  var filtersSection = document.getElementById("navbar-filters-section");
  var summaryWrap = document.getElementById("expenses-summary-wrap");
  var showHamburger = path === "/dashboard" || path === "/expenses" || path === "/expenses/add" || path === "/income" || path === "/income/add" || path === "/recurring" || path === "/link-bank" || path === "/budgets" || path === "/budgets/add" || path === "/reports" || path === "/insights" || path.indexOf("/expenses/") === 0 || path.indexOf("/budgets/") === 0;
  if (filtersToggle && filtersPanel) {
    if (showHamburger) {
      filtersToggle.style.display = "";
    }
    if (filtersSection && path === "/expenses") {
      filtersSection.style.display = "block";
    }
    if (summaryWrap && path === "/expenses") {
      summaryWrap.style.display = "block";
    }
    filtersToggle.addEventListener("click", function() {
      var open = filtersPanel.style.display === "block";
      filtersPanel.style.display = open ? "none" : "block";
      filtersToggle.setAttribute("aria-expanded", open ? "false" : "true");
    });
    document.addEventListener("click", function(e) {
      if (filtersPanel.style.display === "block" && !filtersPanel.contains(e.target) && !filtersToggle.contains(e.target)) {
        filtersPanel.style.display = "none";
        filtersToggle.setAttribute("aria-expanded", "false");
      }
    });
  }
})();
