(function() {
    'use strict';

    var hash = window.location.hash;
    if (hash && hash.indexOf('access_token=') !== -1) {
        var params = new URLSearchParams(hash.slice(1));
        var accessToken = params.get('access_token');
        var refreshToken = params.get('refresh_token');
        if (accessToken) {
            try {
                localStorage.setItem('access_token', accessToken);
                if (refreshToken) {
                    localStorage.setItem('refresh_token', refreshToken);
                }
            } catch (e) {}
            window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
        }
    }

    function applyAuthState() {
        var guest = document.querySelectorAll('.nav-guest');
        var authEls = document.querySelectorAll('.nav-auth');
        var logoutLink = document.getElementById('nav-logout-link');
        if (!window.Auth || !window.Auth.isLoggedIn) {
            return;
        }
        if (window.Auth.isLoggedIn()) {
            if (guest.length) {
                guest.forEach(function(el) {
                    el.style.display = 'none';
                });
            }
            if (authEls.length) {
                authEls.forEach(function(el) {
                    el.style.display = '';
                });
            }
            if (logoutLink) {
                logoutLink.onclick = function(e) {
                    e.preventDefault();
                    window.Auth.logout();
                };
            }
            if (window.Notifications && window.Notifications.start) {
                window.Notifications.start();
            }
            initHouseholdSwitcher();
        } else {
            if (guest.length) {
                guest.forEach(function(el) {
                    el.style.display = '';
                });
            }
            if (authEls.length) {
                authEls.forEach(function(el) {
                    el.style.display = 'none';
                });
            }
        }
    }

    function initHouseholdSwitcher() {
        var wrap = document.getElementById('household-switcher-wrap');
        var sel = document.getElementById('household-switcher');
        if (!wrap || !sel) return;
        var API = window.API_BASE || '';
        var headers = window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
        Promise.all([
            fetch(API + '/api/v1/settings', { headers: headers }).then(function(r) { return r.ok ? r.json() : null; }),
            fetch(API + '/api/v1/households', { headers: headers }).then(function(r) { return r.ok ? r.json() : null; })
        ]).then(function(results) {
            var settings = results[0];
            var households = results[1];
            var activeId = (settings && settings.active_household_id) ? settings.active_household_id : '';
            sel.innerHTML = '<option value="">Personal</option>';
            if (households && households.items && households.items.length) {
                households.items.forEach(function(h) {
                    var opt = document.createElement('option');
                    opt.value = h.household_id || '';
                    opt.textContent = h.name || 'Household';
                    sel.appendChild(opt);
                });
            }
            sel.value = activeId;
            wrap.style.display = 'block';
        }).catch(function() {});
        sel.addEventListener('change', function() {
            var val = sel.value;
            var body = JSON.stringify({ household_id: val || null });
            fetch(API + '/api/v1/settings/active-household', {
                method: 'PATCH',
                headers: Object.assign({ 'Content-Type': 'application/json' }, headers),
                body: body
            }).then(function(r) {
                if (r.ok) window.location.reload();
            });
        });
    }

    var protectedPaths = [
        '/dashboard',
        '/expenses',
        '/expenses/add',
        '/expenses/import',
        '/income',
        '/income/add',
        '/recurring',
        '/link-bank',
        '/budgets',
        '/budgets/add',
        '/reports',
        '/insights',
        '/goals',
        '/goals/add',
        '/investments',
        '/investments/add',
        '/recommendations',
    ];
    var path = window.location.pathname;
    var isProtected = protectedPaths.indexOf(path) !== -1 || path.startsWith('/expenses/') || path.startsWith('/budgets/') || path.startsWith('/goals/') || path.startsWith('/investments/');
    if (isProtected && window.Auth && !window.Auth.isLoggedIn()) {
        window.location.href = '/login?next=' + encodeURIComponent(path);
    } else if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyAuthState);
    } else {
        applyAuthState();
    }

    var filtersToggle = document.getElementById('navbar-filters-toggle');
    var filtersPanel = document.getElementById('navbar-filters-panel');
    var filtersSection = document.getElementById('navbar-filters-section');
    var summaryWrap = document.getElementById('expenses-summary-wrap');
    var showHamburger =
        path === '/dashboard' ||
        path === '/expenses' ||
        path === '/expenses/add' ||
        path === '/income' ||
        path === '/income/add' ||
        path === '/recurring' ||
        path === '/link-bank' ||
        path === '/budgets' ||
        path === '/budgets/add' ||
        path === '/reports' ||
        path === '/insights' ||
        path.indexOf('/expenses/') === 0 ||
        path.indexOf('/budgets/') === 0;
    if (filtersToggle && filtersPanel) {
        if (showHamburger) {
            filtersToggle.style.display = '';
        }
        if (filtersSection && path === '/expenses') {
            filtersSection.style.display = 'block';
        }
        if (summaryWrap && path === '/expenses') {
            summaryWrap.style.display = 'block';
        }
        filtersToggle.addEventListener('click', function() {
            var open = filtersPanel.style.display === 'block';
            filtersPanel.style.display = open ? 'none' : 'block';
            filtersToggle.setAttribute('aria-expanded', open ? 'false' : 'true');
        });
        document.addEventListener('click', function(e) {
            if (
                filtersPanel.style.display === 'block' &&
                !filtersPanel.contains(e.target) &&
                !filtersToggle.contains(e.target)
            ) {
                filtersPanel.style.display = 'none';
                filtersToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }
})();
