/**
 * Teller Connect integration.
 * Loads Teller Connect widget, saves enrollment, syncs transactions.
 */
(function() {
    'use strict';
    var API = window.EXPENSE_API_BASE !== undefined && window.EXPENSE_API_BASE !== ''
        ? window.EXPENSE_API_BASE
        : (window.API_BASE || '');

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

    function getConfig() {
        return request('/api/v1/teller/config');
    }

    function openTellerConnect(onSuccess, onExit, onError) {
        getConfig().then(function(cfg) {
            if (!cfg || !cfg.app_id) {
                if (onError) onError('Teller is not configured on this server.');
                return;
            }
            if (typeof TellerConnect === 'undefined') {
                if (onError) onError('Teller Connect script did not load. Please refresh.');
                return;
            }
            var teller = TellerConnect.setup({
                applicationId: cfg.app_id,
                environment: cfg.environment || 'sandbox',
                onSuccess: function(enrollment) {
                    // enrollment: { accessToken, enrollment: { id, institution: { name } } }
                    var accessToken = enrollment.accessToken;
                    var enrollmentId = (enrollment.enrollment && enrollment.enrollment.id) || '';
                    var institutionName = (enrollment.enrollment && enrollment.enrollment.institution && enrollment.enrollment.institution.name) || '';
                    request('/api/v1/teller/enrollment', {
                        method: 'POST',
                        body: {
                            access_token: accessToken,
                            enrollment_id: enrollmentId,
                            institution_name: institutionName,
                        },
                    }).then(function(data) {
                        if (onSuccess) onSuccess(data);
                    }).catch(function(e) {
                        if (onError) onError(e.message || 'Failed to save Teller enrollment.');
                    });
                },
                onExit: function() {
                    if (onExit) onExit();
                },
            });
            teller.open();
        }).catch(function(e) {
            if (onError) onError(e.message || 'Teller is not available.');
        });
    }

    window.TellerApi = {
        open: openTellerConnect,
        getEnrollments: function() {
            return request('/api/v1/teller/enrollments');
        },
        deleteEnrollment: function(enrollmentId) {
            var headers = {};
            if (window.Auth && window.Auth.getAuthHeaders) {
                Object.assign(headers, window.Auth.getAuthHeaders());
            }
            var doFetch = (window.Auth && window.Auth.requestWithRefresh)
                ? function() { return window.Auth.requestWithRefresh(API + '/api/v1/teller/enrollments/' + encodeURIComponent(enrollmentId), { method: 'DELETE', headers: headers }); }
                : function() { return fetch(API + '/api/v1/teller/enrollments/' + encodeURIComponent(enrollmentId), { method: 'DELETE', headers: headers }); };
            return doFetch().then(function(r) {
                if (!r.ok) throw new Error(r.statusText || 'Request failed');
                return r.json().catch(function() { return {}; });
            });
        },
        sync: function(dateFrom, dateTo) {
            var body = {};
            if (dateFrom) body.date_from = dateFrom;
            if (dateTo) body.date_to = dateTo;
            return request('/api/v1/teller/sync', {
                method: 'POST',
                body: Object.keys(body).length ? body : undefined,
            });
        },
    };
})();
