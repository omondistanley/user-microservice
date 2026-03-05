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

    var protectedPaths = [
        '/dashboard',
        '/expenses',
        '/expenses/add',
        '/income',
        '/income/add',
        '/recurring',
        '/link-bank',
        '/budgets',
        '/budgets/add',
        '/reports',
    ];
    var path = window.location.pathname;
    var isProtected = protectedPaths.indexOf(path) !== -1 || path.startsWith('/expenses/') || path.startsWith('/budgets/');
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
