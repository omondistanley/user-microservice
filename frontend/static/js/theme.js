/**
 * Phase 6: Theme (light/dark/system). Persist in localStorage; apply to body and chart defaults.
 */
(function () {
    'use strict';
    var STORAGE_KEY = 'expense_theme';
    var BODY = document.body || document.documentElement;

    function getStored() {
        try {
            return localStorage.getItem(STORAGE_KEY) || 'dark';
        } catch (e) {
            return 'dark';
        }
    }

    function setStored(value) {
        try {
            localStorage.setItem(STORAGE_KEY, value);
        } catch (e) {}
    }

    function prefersLight() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    }

    function applyTheme(theme) {
        var resolved = theme === 'system' ? (prefersLight() ? 'light' : 'dark') : theme;
        BODY.classList.remove('theme-light', 'theme-dark');
        BODY.classList.add('theme-' + resolved);
        BODY.setAttribute('data-theme', resolved);
        if (window.App && window.App.chartDefaults) {
            window.App.chartDefaults.backgroundColor = resolved === 'light' ? 'rgba(255,255,255,0.9)' : 'rgba(13,13,20,0.9)';
            window.App.chartDefaults.color = resolved === 'light' ? '#374151' : '#e5e7eb';
        }
    }

    function init() {
        var theme = getStored();
        var sel = document.getElementById('theme-select');
        if (sel) {
            sel.value = theme;
            sel.addEventListener('change', function () {
                var v = sel.value;
                setStored(v);
                applyTheme(v);
            });
        }
        applyTheme(theme);
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: light)').addListener(function () {
                if (getStored() === 'system') applyTheme('system');
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    window.Theme = { get: getStored, set: setStored, apply: applyTheme };
})();
