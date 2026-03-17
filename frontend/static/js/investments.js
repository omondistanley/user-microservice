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

    function fetchAlpacaStatus() {
        return fetch(apiUrl('/api/v1/alpaca/status'), { headers: getAuthHeaders() }).then(function (r) {
            if (!r.ok) return { connected: false };
            return r.json();
        }).catch(function () { return { connected: false }; });
    }

    function alpacaSync() {
        return fetch(apiUrl('/api/v1/alpaca/sync'), {
            method: 'POST',
            headers: getAuthHeaders(),
        }).then(function (r) {
            if (!r.ok) throw new Error('Sync failed');
            return r.json();
        });
    }

    function placeOrder(symbol, qty, side) {
        return fetch(apiUrl('/api/v1/alpaca/orders'), {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ symbol: symbol, qty: Number(qty), side: side, type: 'market' }),
        }).then(function (r) {
            if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || 'Order failed'); });
            return r.json();
        });
    }

    function sellHolding(symbol, quantity) {
        if (!confirm('Sell ' + quantity + ' share(s) of ' + symbol + '?')) return Promise.resolve();
        return placeOrder(symbol, quantity, 'sell').then(function () {
            return alpacaSync().catch(function () {}).then(function () { return fetchHoldings(); });
        }).then(function (data) {
            var listEl = document.getElementById('holdings-list');
            if (listEl) renderHoldings(listEl, (data && data.items) ? data.items : []);
        }).catch(function (err) {
            alert(err.message || 'Sell failed');
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
            var source = (h.source || '').toLowerCase();
            html += '<li class="holding-item" data-holding-id="' + (h.holding_id || '') + '" data-symbol="' + escapeHtml(sym) + '" data-quantity="' + qty + '" data-source="' + escapeHtml(source) + '">';
            html += '<div class="holding-symbol">' + escapeHtml(sym) + (source === 'alpaca' ? ' <span class="badge" style="font-size:0.65rem; opacity:0.9;">Alpaca</span>' : '') + '</div>';
            html += '<div class="holding-details">';
            html += '<span class="holding-qty">' + qty + ' @ ' + formatMoney(cost) + ' ' + (h.currency || 'USD') + '</span>';
            if (h.notes) html += '<span class="holding-notes">' + escapeHtml(h.notes) + '</span>';
            html += '</div>';
            html += '<div class="holding-value">' + formatMoney(value) + '</div>';
            if (source === 'alpaca') html += '<button type="button" class="btn btn-sm btn-ghost holding-sell" aria-label="Sell ' + escapeHtml(sym) + '">Sell</button>';
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
        listEl.querySelectorAll('.holding-sell').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var li = btn.closest('.holding-item');
                var sym = li && li.getAttribute('data-symbol');
                var qty = li && li.getAttribute('data-quantity');
                if (sym && qty != null) sellHolding(sym, parseFloat(qty, 10));
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

        function loadHoldings() {
            fetchHoldings().then(function (data) {
                var items = (data && data.items) ? data.items : [];
                renderHoldings(listEl, items);
            }).catch(function () {
                listEl.innerHTML = '<p class="muted">Could not load holdings. Make sure you are logged in.</p>';
            });
        }

        fetchAlpacaStatus().then(function (status) {
            if (status && status.connected) {
                alpacaSync().then(function () { loadHoldings(); }).catch(function () { loadHoldings(); });
            } else {
                loadHoldings();
            }
        }).catch(function () { loadHoldings(); });

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
                    return fetchAlpacaStatus().then(function (status) {
                        if (status && status.connected && confirm('Place this as a buy order on Alpaca? Market order for ' + quantity + ' share(s) of ' + symbol.toUpperCase() + '.')) {
                            return placeOrder(symbol.toUpperCase(), quantity, 'buy').then(function () {
                                alert('Order placed.');
                                return alpacaSync().catch(function () {}).then(function () { return fetchHoldings(); });
                            }).then(function (d) {
                                if (d && d.items) renderHoldings(listEl, d.items);
                            }).catch(function (err) {
                                alert(err.message || 'Order failed');
                            });
                        }
                    });
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

    window.Investments = { fetchHoldings: fetchHoldings, renderHoldings: renderHoldings, sellHolding: sellHolding };
})();
