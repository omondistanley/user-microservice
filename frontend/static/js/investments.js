(function () {
    'use strict';
    var invState = {
        holdings: [],
        quotes: {},
    };

    /** Holdings/market/alpaca/portfolio APIs are routed via the API gateway — always use API_BASE, never EXPENSE_API_BASE. */
    function apiUrl(path) {
        var base = (typeof window !== 'undefined' && window.API_BASE) ? window.API_BASE : '';
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

    /** Gateway JSON with token refresh (falls back to fetch if Auth not loaded). */
    function gatewayJson(path, options) {
        options = options || {};
        if (window.Auth && window.Auth.fetchGatewayJson) {
            return window.Auth.fetchGatewayJson(path, options);
        }
        var url = apiUrl(path);
        var headers = Object.assign({}, getAuthHeaders(), options.headers || {});
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
            options = Object.assign({}, options, { headers: headers, body: JSON.stringify(options.body) });
        } else {
            options = Object.assign({}, options, { headers: headers });
        }
        return fetch(url, options).then(function (r) {
            if (!r.ok) throw new Error(r.statusText || 'Request failed');
            return r.json().catch(function () { return null; });
        });
    }

    function fetchHoldings() {
        return gatewayJson('/api/v1/holdings?page=1&page_size=100').then(function (data) {
            if (!data) throw new Error('Failed to load holdings');
            return data;
        });
    }

    function fetchQuote(symbol) {
        return gatewayJson('/api/v1/market/quote/' + encodeURIComponent(symbol)).catch(function () { return null; });
    }

    function fetchAllQuotes(symbols) {
        // Deduplicate
        var unique = symbols.filter(function (s, i, a) { return a.indexOf(s) === i; });
        return Promise.all(unique.map(function (s) {
            return fetchQuote(s).then(function (q) { return { symbol: s, quote: q }; });
        })).then(function (results) {
            var map = {};
            results.forEach(function (r) { map[r.symbol] = r.quote; });
            return map;
        });
    }

    function createHolding(payload) {
        return gatewayJson('/api/v1/holdings', { method: 'POST', body: payload }).then(function (data) {
            if (!data) throw new Error('Failed to add holding');
            return data;
        });
    }

    function deleteHolding(holdingId) {
        return gatewayJson('/api/v1/holdings/' + holdingId, { method: 'DELETE' }).then(function () {});
    }

    function fetchAlpacaStatus() {
        return gatewayJson('/api/v1/alpaca/status').catch(function () { return { connected: false }; });
    }

    function alpacaSync() {
        return gatewayJson('/api/v1/alpaca/sync', { method: 'POST' });
    }

    function placeOrder(symbol, qty, side) {
        return gatewayJson('/api/v1/alpaca/orders', {
            method: 'POST',
            body: { symbol: symbol, qty: Number(qty), side: side, type: 'market' },
        });
    }

    function sellHolding(symbol, quantity) {
        if (!confirm('Sell ' + quantity + ' share(s) of ' + symbol + '?')) return Promise.resolve();
        return placeOrder(symbol, quantity, 'sell').then(function () {
            return alpacaSync().catch(function () {}).then(function () { return fetchHoldings(); });
        }).then(function (data) {
            var items = (data && data.items) ? data.items : [];
            var listEl = document.getElementById('holdings-list');
            if (listEl) {
                var symbols = items.map(function (h) { return (h.symbol || '').toUpperCase(); });
                fetchAllQuotes(symbols).then(function (quotes) {
                    renderHoldings(listEl, items, quotes);
                });
            }
        }).catch(function (err) {
            alert(err.message || 'Sell failed');
        });
    }

    function formatMoney(n) {
        return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    var INV_GAINS_DAYS = 90;

    function fetchGainsHistory(days) {
        return gatewayJson('/api/v1/portfolio/gains-history?days=' + (days || INV_GAINS_DAYS));
    }

    function placeholderGainsData(message) {
        var dates = [];
        var zeros = [];
        var i;
        for (i = INV_GAINS_DAYS - 1; i >= 0; i--) {
            var d = new Date();
            d.setUTCDate(d.getUTCDate() - i);
            dates.push(d.toISOString().slice(0, 10));
            zeros.push(0);
        }
        return {
            dates: dates,
            series: {
                total: { gain_loss: zeros.slice() },
                manual: { gain_loss: zeros.slice() },
                alpaca: { gain_loss: zeros.slice() },
            },
            note: message || 'No P/L history for this window yet — add or sync holdings to build the curve.',
            _placeholder: true,
        };
    }

    var invGainsChartInstance = null;
    var invGainsLastData = null;

    function renderGainsChart(data, visible) {
        visible = visible || { total: true, manual: false, alpaca: false };
        var container = document.getElementById('inv-gains-chart');
        var noteEl = document.getElementById('inv-gains-note');
        if (!container) return;
        if (invGainsChartInstance) {
            try { invGainsChartInstance.destroy(); } catch (e) {}
            invGainsChartInstance = null;
        }
        if (!data || !data.dates || data.dates.length === 0) {
            data = placeholderGainsData(data && data.note ? data.note : null);
        }
        var series = [];
        if (visible.total && data.series && data.series.total && data.series.total.gain_loss) {
            series.push({ name: 'Total', data: data.series.total.gain_loss });
        }
        if (visible.manual && data.series && data.series.manual && data.series.manual.gain_loss) {
            series.push({ name: 'Manual', data: data.series.manual.gain_loss });
        }
        if (visible.alpaca && data.series && data.series.alpaca && data.series.alpaca.gain_loss) {
            series.push({ name: 'Alpaca', data: data.series.alpaca.gain_loss });
        }
        if (series.length === 0) {
            visible = { total: true, manual: visible.manual, alpaca: visible.alpaca };
            if (data.series && data.series.total && data.series.total.gain_loss) {
                series.push({ name: 'Total', data: data.series.total.gain_loss });
            }
            if (series.length === 0) {
                series.push({ name: 'Total', data: data.dates.map(function () { return 0; }) });
            }
            var tcb = document.getElementById('inv-gains-total');
            if (tcb) tcb.checked = true;
        }
        container.innerHTML = '';
        var gridColor = 'rgba(148,163,184,0.2)';
        if (typeof window !== 'undefined' && document.body && document.body.classList.contains('theme-dark')) {
            gridColor = 'rgba(255,255,255,0.06)';
        }
        var opts = {
            chart: { type: 'line', zoom: { enabled: false }, fontFamily: "'Source Sans 3', sans-serif", toolbar: { show: false }, background: 'transparent' },
            series: series,
            xaxis: { categories: data.dates, labels: { rotate: -45, formatter: function (v) { return (v || '').substring(0, 10); } } },
            yaxis: {
                title: { text: 'Gain / Loss ($)' },
                labels: { formatter: function (v) { return '$' + Number(v).toFixed(0); } }
            },
            stroke: { curve: 'smooth', width: 2 },
            dataLabels: { enabled: false },
            legend: { position: 'top' },
            grid: { borderColor: gridColor },
            colors: ['#6366f1', '#10b981', '#f59e0b']
        };
        if (typeof ApexCharts !== 'undefined') {
            invGainsChartInstance = new ApexCharts(container, opts);
            invGainsChartInstance.render();
        }
        if (noteEl) {
            noteEl.textContent = (data && data.note) ? data.note : 'Based on current holdings and historical prices.';
            noteEl.style.display = 'block';
        }
    }

    function loadGainsChart() {
        fetchGainsHistory(INV_GAINS_DAYS).then(function (data) {
            invGainsLastData = data;
            var visible = invGainsVisible();
            renderGainsChart(data, visible);
        }).catch(function () {
            invGainsLastData = placeholderGainsData('Could not load gains history — showing a placeholder axis. Try again later.');
            var visible = invGainsVisible();
            renderGainsChart(invGainsLastData, visible);
        });
    }

    function invGainsVisible() {
        var totalCb = document.getElementById('inv-gains-total');
        var manualCb = document.getElementById('inv-gains-manual');
        var alpacaCb = document.getElementById('inv-gains-alpaca');
        var total = totalCb ? totalCb.checked : true;
        var manual = manualCb ? manualCb.checked : false;
        var alpaca = alpacaCb ? alpacaCb.checked : false;
        if (!total && !manual && !alpaca) {
            total = true;
            if (totalCb) totalCb.checked = true;
        }
        return { total: total, manual: manual, alpaca: alpaca };
    }

    function formatChangePct(pct) {
        if (pct == null || isNaN(pct)) return '<span class="muted">—</span>';
        var sign = pct >= 0 ? '+' : '';
        var color = pct >= 0 ? 'var(--green,#38a169)' : 'var(--red,#e53e3e)';
        return '<span style="color:' + color + ';font-weight:600;">' + sign + Number(pct).toFixed(2) + '%</span>';
    }

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function renderHoldings(listEl, items, quotes) {
        quotes = quotes || {};
        invState.holdings = items || [];
        invState.quotes = quotes;
        if (!listEl) return;
        if (!items || items.length === 0) {
            listEl.innerHTML = '<p class="muted">No holdings yet. Click "Add holding" to track a position.</p>';
            return;
        }

        var totalMarketValue = 0;
        var totalCostBasis = 0;
        var totalDayChangeDollars = 0;
        var html = '<ul class="holdings-items">';

        items.forEach(function (h) {
            var qty = Number(h.quantity);
            var cost = Number(h.avg_cost);
            var sym = (h.symbol || '').toUpperCase();
            var source = (h.source || '').toLowerCase();
            var q = quotes[sym];
            var price = q && q.price != null ? Number(q.price) : null;
            var changePct = q && q.change_pct != null ? Number(q.change_pct) : null;
            var marketValue = price != null ? qty * price : qty * cost;
            var costBasis = qty * cost;
            var dayChangeDollars = (price != null && changePct != null)
                ? marketValue * (changePct / 100) / (1 + changePct / 100)
                : 0;

            totalMarketValue += marketValue;
            totalCostBasis += costBasis;
            totalDayChangeDollars += dayChangeDollars;

            html += '<li class="holding-item"'
                + ' data-holding-id="' + escapeHtml(h.holding_id || '') + '"'
                + ' data-symbol="' + escapeHtml(sym) + '"'
                + ' data-quantity="' + qty + '"'
                + ' data-source="' + escapeHtml(source) + '"'
                + ' data-cost="' + cost + '"'
                + ' data-price="' + (price != null ? price : '') + '"'
                + ' data-change-pct="' + (changePct != null ? changePct : '') + '"'
                + '>';
            html += '<div class="holding-symbol">' + escapeHtml(sym)
                + (source === 'alpaca' ? ' <span class="badge" style="font-size:0.65rem;opacity:0.9;">Alpaca</span>' : '') + '</div>';
            html += '<div class="holding-details">';
            html += '<span class="holding-qty">' + qty + ' @ ' + formatMoney(cost).replace('$','') + ' ' + (h.currency || 'USD') + '</span>';
            if (h.notes) html += '<span class="holding-notes">' + escapeHtml(h.notes) + '</span>';
            html += '</div>';
            html += '<div class="holding-value">' + formatMoney(marketValue) + '</div>';
            if (source === 'alpaca') {
                html += '<button type="button" class="btn btn-sm btn-ghost holding-sell" aria-label="Sell ' + escapeHtml(sym) + '">Sell</button>';
            } else {
                html += '<button type="button" class="btn btn-sm btn-ghost holding-delete" aria-label="Remove ' + escapeHtml(sym) + '">Remove</button>';
            }
            html += '</li>';
        });
        html += '</ul>';

        // Store aggregates on listEl for the template sync to pick up
        listEl._totalMarketValue = totalMarketValue;
        listEl._totalDayChangeDollars = totalDayChangeDollars;
        listEl._totalCostBasis = totalCostBasis;
        listEl._quotes = quotes;
        listEl.innerHTML = html;

        listEl.querySelectorAll('.holding-delete').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var li = btn.closest('.holding-item');
                var id = li && li.getAttribute('data-holding-id');
                if (!id || !confirm('Remove this holding?')) return;
                deleteHolding(id).then(function () {
                    li.remove();
                    if (listEl.querySelectorAll('.holding-item').length === 0) {
                        listEl.innerHTML = '<p class="muted">No holdings yet. Click "Add holding" to track a position.</p>';
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
                if (sym && qty != null) sellHolding(sym, parseFloat(qty));
            });
        });
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

        var invTbody = document.getElementById('inv-holdings-table-body');
        if (invTbody) {
            invTbody.innerHTML = '<tr><td colspan="8" style="padding:1rem;"><div class="skeleton-line skeleton-line--wide"></div><div class="skeleton-line skeleton-line--medium" style="margin-top:10px;"></div></td></tr>';
        }

        function loadHoldings() {
            fetchHoldings().then(function (data) {
                var items = (data && data.items) ? data.items : [];
                var symbols = items.map(function (h) { return (h.symbol || '').toUpperCase(); });
                return fetchAllQuotes(symbols).then(function (quotes) {
                    invState.holdings = items;
                    invState.quotes = quotes;
                    renderHoldings(listEl, items, quotes);
                });
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

        loadGainsChart();

        var gainsCollapse = document.getElementById('inv-gains-collapse-toggle');
        var gainsBody = document.getElementById('inv-gains-body');
        if (gainsCollapse && gainsBody) {
            gainsCollapse.addEventListener('click', function () {
                var hidden = gainsBody.getAttribute('data-collapsed') === '1';
                if (hidden) {
                    gainsBody.style.display = '';
                    gainsBody.setAttribute('data-collapsed', '0');
                    gainsCollapse.textContent = 'Hide chart';
                    gainsCollapse.setAttribute('aria-expanded', 'true');
                    if (invGainsLastData) renderGainsChart(invGainsLastData, invGainsVisible());
                } else {
                    gainsBody.style.display = 'none';
                    gainsBody.setAttribute('data-collapsed', '1');
                    gainsCollapse.textContent = 'Show chart';
                    gainsCollapse.setAttribute('aria-expanded', 'false');
                }
            });
        }

        ['inv-gains-total', 'inv-gains-manual', 'inv-gains-alpaca'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('change', function () {
                if (invGainsLastData) renderGainsChart(invGainsLastData, invGainsVisible());
            });
        });

        var addBtn = document.getElementById('holdings-add-btn');
        if (addBtn) addBtn.addEventListener('click', showAddForm);

        var addParam = typeof URLSearchParams !== 'undefined' && window.location.search
            ? new URLSearchParams(window.location.search).get('add') : null;
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
                var symbol = ((document.getElementById('holding-symbol') || {}).value || '').trim();
                var quantity = parseFloat((document.getElementById('holding-quantity') || {}).value);
                var avgCost = parseFloat((document.getElementById('holding-avg-cost') || {}).value);
                var currency = (((document.getElementById('holding-currency') || {}).value) || 'USD').trim().toUpperCase();
                var notes = (((document.getElementById('holding-notes') || {}).value) || '').trim() || null;
                if (!symbol || isNaN(quantity) || quantity <= 0 || isNaN(avgCost) || avgCost < 0) {
                    alert('Please fill symbol, quantity (positive), and avg. cost (≥ 0).');
                    return;
                }
                var payload = { symbol: symbol, quantity: quantity, avg_cost: avgCost, currency: currency || 'USD' };
                if (notes) payload.notes = notes;
                createHolding(payload).then(function () {
                    hideAddForm();
                    form.reset();
                    var cur = document.getElementById('holding-currency');
                    if (cur) cur.value = 'USD';
                    return fetchHoldings();
                }).then(function (data) {
                    var items = (data && data.items) ? data.items : [];
                    var symbols = items.map(function (h) { return (h.symbol || '').toUpperCase(); });
                    return fetchAllQuotes(symbols).then(function (quotes) {
                        renderHoldings(listEl, items, quotes);
                        return fetchAlpacaStatus().then(function (status) {
                            if (status && status.connected &&
                                confirm('Place this as a buy order on Alpaca? Market order for ' + quantity + ' share(s) of ' + symbol.toUpperCase() + '.')) {
                                return placeOrder(symbol.toUpperCase(), quantity, 'buy').then(function () {
                                    alert('Order placed.');
                                    return alpacaSync().catch(function () {}).then(function () { return fetchHoldings(); });
                                }).then(function (d) {
                                    if (d && d.items) {
                                        var syms2 = d.items.map(function (h) { return (h.symbol || '').toUpperCase(); });
                                        return fetchAllQuotes(syms2).then(function (q2) {
                                            renderHoldings(listEl, d.items, q2);
                                        });
                                    }
                                }).catch(function (err) {
                                    alert(err.message || 'Order failed');
                                });
                            }
                        });
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
