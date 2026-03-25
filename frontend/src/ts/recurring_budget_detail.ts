// @ts-nocheck
(function () {
    'use strict';
    var API = window.API_BASE || '';
    var wrap = document.querySelector('[data-recurring-id]');
    var rid = wrap && wrap.getAttribute('data-recurring-id');

    function headers(isJson) {
        var h = window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
        if (isJson) h['Content-Type'] = 'application/json';
        return h;
    }

    function render(d) {
        var el = document.getElementById('rb-detail');
        if (!el || !d) return;
        el.innerHTML = '<p><strong>Amount</strong> $' + esc(d.amount) + '</p>' +
            '<p><strong>Cadence</strong> ' + esc(d.cadence) + '</p>' +
            '<p><strong>Category</strong> ' + esc(d.category_code) + ' — ' + esc(d.category_name) + '</p>' +
            '<p><strong>Next period</strong> ' + esc(d.next_period_start) + '</p>' +
            '<p><strong>Active</strong> ' + (d.is_active ? 'Yes' : 'No') + '</p>';
    }

    function esc(s) {
        if (s == null) return '';
        var x = document.createElement('div');
        x.textContent = String(s);
        return x.innerHTML;
    }

    function load() {
        if (!rid) return;
        fetch(API + '/api/v1/recurring-budgets/' + encodeURIComponent(rid), { headers: headers(false) })
            .then(function (r) { if (!r.ok) throw new Error('x'); return r.json(); })
            .then(render)
            .catch(function () {
                var el = document.getElementById('rb-detail');
                if (el) el.textContent = 'Not found or failed to load.';
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        load();
        var msg = document.getElementById('rb-detail-msg');
        var tog = document.getElementById('rb-toggle-active');
        var del = document.getElementById('rb-delete');
        if (!rid || !tog || !del) return;
        tog.addEventListener('click', function () {
            fetch(API + '/api/v1/recurring-budgets/' + encodeURIComponent(rid), { headers: headers(false) })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    return fetch(API + '/api/v1/recurring-budgets/' + encodeURIComponent(rid), {
                        method: 'PATCH',
                        headers: headers(true),
                        body: JSON.stringify({ is_active: !d.is_active }),
                    });
                })
                .then(function (r) {
                    if (!r.ok) throw new Error('x');
                    return r.json();
                })
                .then(function (d) {
                    render(d);
                    if (msg) msg.textContent = 'Updated.';
                })
                .catch(function () { if (msg) msg.textContent = 'Update failed.'; });
        });
        del.addEventListener('click', function () {
            if (!confirm('Delete this recurring budget?')) return;
            fetch(API + '/api/v1/recurring-budgets/' + encodeURIComponent(rid), { method: 'DELETE', headers: headers(false) })
                .then(function (r) {
                    if (r.status === 204) window.location.href = '/budgets/recurring';
                    else if (msg) msg.textContent = 'Delete failed.';
                })
                .catch(function () { if (msg) msg.textContent = 'Delete failed.'; });
        });
    });
})();
