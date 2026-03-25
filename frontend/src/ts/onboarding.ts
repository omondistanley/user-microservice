// @ts-nocheck
/**
 * Phase 6: First-session onboarding banner. Dismissible once per device (localStorage).
 */
(function () {
    'use strict';
    var KEY = 'expense_onboarding_dismissed';

    function wasDismissed() {
        try {
            return localStorage.getItem(KEY) === '1';
        } catch (e) {
            return false;
        }
    }

    function setDismissed() {
        try {
            localStorage.setItem(KEY, '1');
        } catch (e) {}
    }

    function init() {
        var banner = document.getElementById('onboarding-banner');
        var dismiss = document.getElementById('onboarding-dismiss');
        if (!banner) return;
        if (wasDismissed()) {
            banner.style.display = 'none';
            return;
        }
        if (window.Auth && window.Auth.isLoggedIn && window.Auth.isLoggedIn()) {
            banner.style.display = 'block';
        }
        if (dismiss) {
            dismiss.addEventListener('click', function () {
                setDismissed();
                banner.style.display = 'none';
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
