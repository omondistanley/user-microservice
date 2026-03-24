(function () {
    'use strict';
    var API = window.API_BASE || '';

    function headers(jsonBody) {
        var h = window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
        if (jsonBody) h['Content-Type'] = 'application/json';
        return h;
    }

    function load() {
        var el = document.getElementById('rb-list');
        if (!el) return;
        fetch(API + '/api/v1/recurring-budgets?page_size=50', { headers: headers(false) })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                var items = (d && d.items) || [];
                el.innerHTML = items.map(function (it) {
                    var id = it.recurring_budget_id || it.id;
                    return '<div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">' +
                        '<div><p class="font-semibold text-slate-900 dark:text-white">' + esc(it.name || 'Recurring') + '</p>' +
                        '<p class="text-sm text-slate-500">' + esc(it.cadence) + ' · cat ' + esc(it.category_code) + ' · $' + esc(it.amount) + '</p></div>' +
                        '<a href="/budgets/recurring/' + encodeURIComponent(id) + '" class="text-[#135bec] text-sm font-semibold">View</a></div>';
                }).join('') || '<p class="text-slate-500">No recurring budgets yet.</p>';
            })
            .catch(function () {
                el.innerHTML = '<p class="text-rose-600">Failed to load.</p>';
            });
    }

    function esc(s) {
        if (s == null) return '';
        var d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    document.addEventListener('DOMContentLoaded', function () {
        load();
        var form = document.getElementById('rb-create');
        if (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                var fd = new FormData(form);
                var body = {
                    name: fd.get('name') || null,
                    amount: fd.get('amount'),
                    category_code: parseInt(fd.get('category_code'), 10),
                    cadence: fd.get('cadence'),
                    start_date: fd.get('start_date'),
                };
                var msg = document.getElementById('rb-msg');
                fetch(API + '/api/v1/recurring-budgets', { method: 'POST', headers: headers(true), body: JSON.stringify(body) })
                    .then(function (r) {
                        if (!r.ok) throw new Error('save');
                        return r.json();
                    })
                    .then(function () {
                        if (msg) msg.textContent = 'Saved.';
                        form.reset();
                        load();
                    })
                    .catch(function () {
                        if (msg) msg.textContent = 'Could not create.';
                    });
            });
        }
    });
})();
