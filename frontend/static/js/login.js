/**
 * Login page: URL param messages, form submit via fetch (no full-page POST).
 * Depends on auth.js (window.Auth). Load after auth.js.
 * Uses DOMContentLoaded and event delegation so the button works regardless of load order.
 */
(function() {
    'use strict';

    var params = new URLSearchParams(window.location.search);

    function runWhenReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    runWhenReady(function init() {
        var msg = document.getElementById('login-message');

        // Security: strip email/password from URL if present
        var hasSensitive = params.has('email') || params.has('password');
        if (hasSensitive && window.history && window.history.replaceState) {
            var clean = new URLSearchParams(window.location.search);
            clean.delete('email');
            clean.delete('password');
            var qs = clean.toString();
            var url = window.location.pathname + (qs ? '?' + qs : '') + window.location.hash;
            window.history.replaceState({}, document.title, url);
            params = new URLSearchParams(window.location.search);
        }

        var statusMap = {
            session_expired: 'Your session expired. Please sign in again.',
            access_denied: 'Sign-in cancelled.',
            invalid_state: 'Invalid state — please try again.',
            token_exchange_failed: 'Sign-in failed. Please try again.',
            no_email: 'No email returned from provider.',
            no_apple_email: 'Apple did not share your email.',
            server: 'Server error — please try again.',
            google_not_configured: 'Google sign-in is not set up. Use email & password.',
            apple_not_configured: 'Apple sign-in is not set up. Use email & password.'
        };

        function showAlert(text, isSuccess) {
            var m = document.getElementById('login-message');
            if (!m) return;
            m.textContent = text;
            m.className = 'auth-alert ' + (isSuccess ? 'auth-alert--success' : 'auth-alert--error');
            m.style.display = 'block';
        }

        if (msg) {
            if (params.get('session') === 'expired') {
                showAlert(statusMap.session_expired, false);
            } else if (params.get('error')) {
                showAlert(statusMap[params.get('error')] || 'Sign-in failed. Try again.', false);
            } else if (params.get('verified') === '1') {
                showAlert('Email verified — you can sign in now.', true);
            } else if (params.get('verified') === '0') {
                showAlert('Verification link is invalid or expired.', false);
            }
        }

        function doLogin(btnId, emailId, passwordId, msgId) {
            if (!window.Auth) {
                showAlert('Sign-in is loading. Please try again.', false);
                return;
            }
            var emailEl    = document.getElementById(emailId);
            var passwordEl = document.getElementById(passwordId);
            if (!emailEl || !passwordEl) return;
            var email    = (emailEl.value || '').trim();
            var password = passwordEl.value || '';
            if (!email)    { showAlert('Please enter your email.',    false); return; }
            if (!password) { showAlert('Please enter your password.', false); return; }
            var m = document.getElementById(msgId);
            if (m) m.style.display = 'none';
            var submitBtn = document.getElementById(btnId);
            if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Signing in…'; }
            window.Auth.login(email, password).then(function(data) {
                if (data && data.access_token) {
                    try {
                        localStorage.setItem('access_token', data.access_token);
                        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
                    } catch (err) {}
                    var next = params.get('next');
                    var target = '/dashboard';
                    if (next && next.startsWith('/') && next.indexOf('//') === -1) target = next;
                    window.location.href = target;
                } else {
                    showAlert('Invalid response from server. Please try again.', false);
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Sign in'; }
                }
            }).catch(function(err) {
                showAlert(err.message || 'Login failed', false);
                if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Sign in'; }
            });
        }

        // Event delegation: desktop button + mobile button
        document.body.addEventListener('click', function(e) {
            if (e.target && e.target.id === 'login-submit-btn') {
                e.preventDefault();
                doLogin('login-submit-btn', 'email', 'password', 'login-message');
            }
            if (e.target && e.target.id === 'login-submit-btn-mobile') {
                e.preventDefault();
                doLogin('login-submit-btn-mobile', 'email-m', 'password-m', 'login-message-mobile');
            }
        });
        document.body.addEventListener('submit', function(e) {
            if (e.target && e.target.id === 'login-form') {
                e.preventDefault();
                e.stopPropagation();
                doLogin();
            }
        });

        // Password toggle
        var toggle = document.getElementById('login-password-toggle');
        var pw = document.getElementById('password');
        if (toggle && pw) {
            toggle.addEventListener('click', function() {
                var hidden = pw.type === 'password';
                pw.type = hidden ? 'text' : 'password';
                toggle.textContent = hidden ? 'Hide' : 'Show';
            });
        }
    });
})();
