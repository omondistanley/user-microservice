(function () {
    'use strict';

    var API_BASE = '';
    function apiUrl(path) {
        var base = (typeof window !== 'undefined' && window.EXPENSE_API_BASE) ? window.EXPENSE_API_BASE : API_BASE;
        return (base || '') + path;
    }

    function getAuthHeaders() {
        if (window.Auth && window.Auth.getAuthHeaders) {
            var h = window.Auth.getAuthHeaders();
            if (Object.keys(h).length) {
                h['Content-Type'] = 'application/json';
                return h;
            }
        }
        var token = window.Auth && window.Auth.getToken && window.Auth.getToken();
        if (!token) return {};
        return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
    }

    function fetchHoldings() {
        var url = apiUrl('/api/v1/holdings') + '?page=1&page_size=100';
        return fetch(url, { headers: getAuthHeaders() }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load holdings');
            return r.json();
        });
    }

    function createHolding(payload) {
        return fetch(apiUrl('/api/v1/holdings'), {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload),
        }).then(function (r) {
            if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || 'Failed to add holding'); });
            return r.json();
        });
    }

    function deleteHolding(holdingId) {
        return fetch(apiUrl('/api/v1/holdings/' + holdingId), {
            method: 'DELETE',
            headers: getAuthHeaders(),
        }).then(function (r) {
            if (!r.ok) throw new Error('Failed to delete');
        });
    }

    function renderHoldings(listEl, items) {
        if (!listEl) return;
        if (!items || items.length === 0) {
            listEl.innerHTML = '<p class="muted">No holdings yet. Click “Add holding” to track a position.</p>';
            return;
        }
        var totalCost = 0;
        var html = '<ul class="holdings-items">';
        items.forEach(function (h) {
            var qty = Number(h.quantity);
            var cost = Number(h.avg_cost);
            var value = qty * cost;
            totalCost += value;
            var sym = (h.symbol || '').toUpperCase();
            html += '<li class="holding-item" data-holding-id="' + (h.holding_id || '') + '">';
            html += '<div class="holding-symbol">' + escapeHtml(sym) + '</div>';
            html += '<div class="holding-details">';
            html += '<span class="holding-qty">' + qty + ' @ ' + formatMoney(cost) + ' ' + (h.currency || 'USD') + '</span>';
            if (h.notes) html += '<span class="holding-notes">' + escapeHtml(h.notes) + '</span>';
            html += '</div>';
            html += '<div class="holding-value">' + formatMoney(value) + '</div>';
            html += '<button type="button" class="btn btn-sm btn-ghost holding-delete" aria-label="Delete ' + escapeHtml(sym) + '">Delete</button>';
            html += '</li>';
        });
        html += '</ul>';
        listEl.innerHTML = html;

        listEl.querySelectorAll('.holding-delete').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var li = btn.closest('.holding-item');
                var id = li && li.getAttribute('data-holding-id');
                if (!id || !confirm('Remove this holding?')) return;
                deleteHolding(id).then(function () {
                    li.remove();
                    if (listEl.querySelectorAll('.holding-item').length === 0) {
                        listEl.innerHTML = '<p class="muted">No holdings yet. Click “Add holding” to track a position.</p>';
                    }
                }).catch(function (err) {
                    alert(err.message || 'Delete failed');
                });
            });
        });
    }

    function formatMoney(n) {
        return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function showAddForm() {
        var wrap = document.getElementById('add-holding-form-wrap');
        if (wrap) {
            wrap.style.display = 'block';
            wrap.setAttribute('aria-hidden', 'false');
        }
    }

    function hideAddForm() {
        var wrap = document.getElementById('add-holding-form-wrap');
        if (wrap) {
            wrap.style.display = 'none';
            wrap.setAttribute('aria-hidden', 'true');
        }
    }

    function init() {
        var listEl = document.getElementById('holdings-list');
        if (!listEl) return;

        fetchHoldings().then(function (data) {
            var items = (data && data.items) ? data.items : [];
            renderHoldings(listEl, items);
        }).catch(function () {
            listEl.innerHTML = '<p class="muted">Could not load holdings. Make sure you are logged in.</p>';
        });

        var addBtn = document.getElementById('holdings-add-btn');
        if (addBtn) addBtn.addEventListener('click', showAddForm);

        var addParam = typeof URLSearchParams !== 'undefined' && window.location.search ? new URLSearchParams(window.location.search).get('add') : null;
        if (addParam && addParam.trim()) {
            var symInput = document.getElementById('holding-symbol');
            if (symInput) symInput.value = addParam.trim().toUpperCase();
            showAddForm();
        }

        var cancelBtn = document.getElementById('add-holding-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', hideAddForm);

        var backdrop = document.getElementById('add-holding-backdrop');
        if (backdrop) backdrop.addEventListener('click', hideAddForm);

        var form = document.getElementById('add-holding-form');
        if (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                var symbol = (document.getElementById('holding-symbol') && document.getElementById('holding-symbol').value || '').trim();
                var quantity = parseFloat(document.getElementById('holding-quantity') && document.getElementById('holding-quantity').value, 10);
                var avgCost = parseFloat(document.getElementById('holding-avg-cost') && document.getElementById('holding-avg-cost').value, 10);
                var currency = (document.getElementById('holding-currency') && document.getElementById('holding-currency').value || 'USD').trim().toUpperCase();
                var notes = (document.getElementById('holding-notes') && document.getElementById('holding-notes').value || '').trim() || null;
                if (!symbol || isNaN(quantity) || quantity <= 0 || isNaN(avgCost) || avgCost < 0) {
                    alert('Please fill symbol, quantity (positive), and avg. cost (≥ 0).');
                    return;
                }
                var payload = { symbol: symbol, quantity: quantity, avg_cost: avgCost, currency: currency || 'USD' };
                if (notes) payload.notes = notes;
                createHolding(payload).then(function () {
                    hideAddForm();
                    form.reset();
                    if (document.getElementById('holding-currency')) document.getElementById('holding-currency').value = 'USD';
                    return fetchHoldings();
                }).then(function (data) {
                    renderHoldings(listEl, (data && data.items) ? data.items : []);
                }).catch(function (err) {
                    alert(err.message || 'Failed to add holding');
                });
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.Investments = { fetchHoldings: fetchHoldings, renderHoldings: renderHoldings };
})();
