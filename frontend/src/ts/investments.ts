// @ts-nocheck
(function () {
    'use strict';
    var invState = {
        holdings: [],
        quotes: {},
    };

    function showNotice(message, tone) {
        if (!message) return;
        var box = document.getElementById('inv-inline-notice');
        if (!box) {
            box = document.createElement('div');
            box.id = 'inv-inline-notice';
            box.className = 'note';
            box.style.marginBottom = '0.75rem';
            var main = document.querySelector('.content-area') || document.querySelector('main') || document.body;
            if (main.firstChild) main.insertBefore(box, main.firstChild);
            else main.appendChild(box);
        }
        box.textContent = String(message);
        box.style.display = 'block';
        box.style.borderLeftColor = tone === 'error' ? '#e53e3e' : (tone === 'success' ? '#38a169' : '#38bdf8');
        clearTimeout(showNotice._timer);
        showNotice._timer = setTimeout(function () {
            box.style.display = 'none';
            box.textContent = '';
        }, 3500);
    }

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
            showNotice(err.message || 'Sell failed', 'error');
        });
    }

    function formatMoney(n) {
        return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    var INV_GAINS_DAYS = 90;
    var invGainsChartType = 'line';
    var _invReturnMethod = 'pl'; // pl | twr | mwr

    function fetchGainsHistory(days) {
        var method = _invReturnMethod !== 'pl' ? ('&return_method=' + _invReturnMethod) : '';
        return gatewayJson('/api/v1/portfolio/gains-history?days=' + (days || INV_GAINS_DAYS) + method);
    }

    document.addEventListener('inv:returnMethodChange', function(e) {
        var method = (e as CustomEvent).detail && (e as CustomEvent).detail.method;
        if (!method) return;
        _invReturnMethod = method;
        fetchGainsHistory(INV_GAINS_DAYS).then(function(data) {
            invGainsLastData = data;
            renderGainsChart(data, invGainsVisible());
        }).catch(function() {});
    });

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
            chart: { type: invGainsChartType, zoom: { enabled: false }, fontFamily: "'Source Sans 3', sans-serif", toolbar: { show: false }, background: 'transparent' },
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

            var unrealized = price != null ? (marketValue - costBasis) : null;
            var roleLabel = (h.role_label || '').toString();
            html += '<li class="holding-item"'
                + ' data-holding-id="' + escapeHtml(h.holding_id || '') + '"'
                + ' data-symbol="' + escapeHtml(sym) + '"'
                + ' data-quantity="' + qty + '"'
                + ' data-source="' + escapeHtml(source) + '"'
                + ' data-cost="' + cost + '"'
                + ' data-price="' + (price != null ? price : '') + '"'
                + ' data-change-pct="' + (changePct != null ? changePct : '') + '"'
                + ' data-role="' + escapeHtml(roleLabel) + '"'
                + ' data-unrealized="' + (unrealized != null ? unrealized : '') + '"'
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
                    showNotice(err.message || 'Delete failed', 'error');
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
            invTbody.innerHTML = '<tr><td colspan="10" style="padding:1rem;"><div class="skeleton-line skeleton-line--wide"></div><div class="skeleton-line skeleton-line--medium" style="margin-top:10px;"></div></td></tr>';
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

        // Period selector buttons
        document.querySelectorAll('.inv-period-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.inv-period-btn').forEach(function (b) { b.classList.remove('inv-period-btn--active'); });
                btn.classList.add('inv-period-btn--active');
                var days = parseInt(btn.getAttribute('data-days') || '90', 10);
                var fetchDays = days === 0 ? 1825 : days;
                INV_GAINS_DAYS = fetchDays;
                fetchGainsHistory(fetchDays).then(function (data) {
                    invGainsLastData = data;
                    renderGainsChart(data, invGainsVisible());
                }).catch(function () {
                    invGainsLastData = placeholderGainsData('Could not load gains history for this period. Try again later.');
                    renderGainsChart(invGainsLastData, invGainsVisible());
                });
            });
        });

        // Chart type toggle buttons
        document.querySelectorAll('.inv-chart-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.inv-chart-type-btn').forEach(function (b) { b.classList.remove('inv-chart-type-btn--active'); });
                btn.classList.add('inv-chart-type-btn--active');
                invGainsChartType = btn.getAttribute('data-type') || 'line';
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
                    showNotice('Please fill symbol, quantity (positive), and avg. cost (>= 0).', 'error');
                    return;
                }
                var accountType = (((document.getElementById('holding-account-type') || {}).value) || 'taxable').trim();
                var payload = { symbol: symbol, quantity: quantity, avg_cost: avgCost, currency: currency || 'USD', account_type: accountType };
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
                                    showNotice('Order placed.', 'success');
                                    return alpacaSync().catch(function () {}).then(function () { return fetchHoldings(); });
                                }).then(function (d) {
                                    if (d && d.items) {
                                        var syms2 = d.items.map(function (h) { return (h.symbol || '').toUpperCase(); });
                                        return fetchAllQuotes(syms2).then(function (q2) {
                                            renderHoldings(listEl, d.items, q2);
                                        });
                                    }
                                }).catch(function (err) {
                                    showNotice(err.message || 'Order failed', 'error');
                                });
                            }
                        });
                    });
                }).catch(function (err) {
                    showNotice(err.message || 'Failed to add holding', 'error');
                });
            });
        }
    }

    // ── Portfolio Health Score ──────────────────────────────────────────────

    function fetchPortfolioHealth() {
        return gatewayJson('/api/v1/portfolio/health').catch(function () { return null; });
    }

    function renderHealthScore(data) {
        if (!data) return;
        var scoreLabel = document.getElementById('inv-health-score-label');
        var barFill = document.getElementById('inv-health-bar-fill');
        var badge = document.getElementById('inv-health-badge');
        var headline = document.getElementById('inv-health-headline');
        var components = document.getElementById('inv-health-components');
        var flags = document.getElementById('inv-health-flags');

        var score = data.score || 0;
        var tier = data.tier || 'amber';
        var tierColors = { green: '#38a169', amber: '#ecc94b', red: '#e53e3e' };
        var color = tierColors[tier] || tierColors.amber;

        if (scoreLabel) scoreLabel.textContent = score + '/100';
        if (barFill) barFill.style.width = score + '%';
        if (badge) {
            badge.textContent = tier.charAt(0).toUpperCase() + tier.slice(1);
            badge.style.background = color;
            badge.style.color = '#fff';
            badge.style.padding = '2px 10px';
            badge.style.borderRadius = '99px';
        }
        if (headline) headline.textContent = data.headline || '';

        if (components && data.components) {
            var html = '';
            Object.keys(data.components).forEach(function (key) {
                var c = data.components[key];
                var cScore = Math.round(c.score || 0);
                var cColor = cScore >= 70 ? '#38a169' : (cScore >= 40 ? '#ecc94b' : '#e53e3e');
                html += '<div style="background:var(--surface-alt,#f8fafc);border-radius:6px;padding:0.5rem 0.75rem;">';
                html += '<div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:0.2rem;">' + escapeHtml(c.label || key) + '</div>';
                html += '<div style="font-weight:700;font-size:1rem;color:' + cColor + ';">' + cScore + '</div>';
                html += '</div>';
            });
            components.innerHTML = html;
        }

        if (flags && data.flags && data.flags.length) {
            flags.innerHTML = data.flags.map(function (f) {
                return '<span style="display:inline-block;margin-right:0.5rem;margin-bottom:0.25rem;background:#fef3c7;border-radius:4px;padding:2px 8px;font-size:0.78rem;">⚠ ' + escapeHtml(f) + '</span>';
            }).join('');
        }
    }

    // ── Finance Context Strip ────────────────────────────────────────────────

    function fetchSurplus() {
        var gw = (typeof window !== 'undefined' && window.API_BASE) ? window.API_BASE : '';
        var expenseBase = (typeof window !== 'undefined' && window.EXPENSE_API_BASE) ? window.EXPENSE_API_BASE : '';
        var url = (gw || expenseBase || '') + '/api/v1/surplus';
        return fetch(url, { headers: getAuthHeaders() })
            .then(function (r) { return r.ok ? r.json() : null; })
            .catch(function () { return null; });
    }

    function renderFinanceStrip(surplus) {
        var strip = document.getElementById('finance-context-strip');
        var text = document.getElementById('finance-context-text');
        if (!strip || !text) return;
        if (!surplus) return;
        var s = parseFloat(surplus.investable_surplus || 0);
        var fmt = function (n) { return '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }); };
        if (s > 0) {
            text.textContent = 'You have approximately ' + fmt(s) + ' available this month after your bills and goals. View your portfolio for investment context.';
        } else if (s < 0) {
            text.textContent = 'Your tracked spending exceeded income by ' + fmt(s) + ' this month. This is informational — some transactions may not be captured.';
        } else {
            return;
        }
        strip.style.display = 'block';
    }

    var NORTH_STAR_CACHE_KEY = 'pocketii_north_star_v1';
    var NORTH_STAR_TTL_MS = 5 * 60 * 1000;

    function readNorthStarCache() {
        try {
            var raw = sessionStorage.getItem(NORTH_STAR_CACHE_KEY);
            if (!raw) return null;
            var o = JSON.parse(raw);
            if (!o || !o.ts || (Date.now() - o.ts) > NORTH_STAR_TTL_MS) return null;
            return o.data || null;
        } catch (e) { return null; }
    }

    function writeNorthStarCache(data) {
        try { sessionStorage.setItem(NORTH_STAR_CACHE_KEY, JSON.stringify({ ts: Date.now(), data: data })); } catch (e) {}
    }

    function sectorGapFromPrefs(prefs, sectorRows) {
        if (!sectorRows || !sectorRows.length) return null;
        var prefsList = (prefs || []).map(function (p) { return String(p).toLowerCase().trim(); }).filter(Boolean);
        function matchPct(pref) {
            var best = 0;
            sectorRows.forEach(function (s) {
                var name = String(s.name != null ? s.name : s.sector || '').toLowerCase();
                var p = parseFloat(s.pct != null ? s.pct : s.percent || 0);
                if (!name || !isFinite(p)) return;
                if (name.indexOf(pref) !== -1 || pref.indexOf(name) !== -1) {
                    if (p > best) best = p;
                }
            });
            return best;
        }
        if (prefsList.length) {
            var share = 100 / prefsList.length;
            var bestGap = 0;
            var bestName = null;
            prefsList.forEach(function (pref) {
                var actual = matchPct(pref);
                var gap = share - actual;
                if (gap > bestGap && gap >= 2) {
                    bestGap = gap;
                    bestName = pref;
                }
            });
            if (bestName) {
                var pretty = bestName.charAt(0).toUpperCase() + bestName.slice(1);
                return { label: pretty, gapPct: Math.round(bestGap) };
            }
        }
        var n = sectorRows.length;
        var eq = 100 / n;
        var worst = null;
        var worstGap = 0;
        sectorRows.forEach(function (s) {
            var name = String(s.name != null ? s.name : s.sector || '');
            var p = parseFloat(s.pct != null ? s.pct : s.percent || 0);
            if (!name || !isFinite(p)) return;
            var gap = eq - p;
            if (gap > worstGap && gap >= 3) {
                worstGap = gap;
                worst = name;
            }
        });
        return worst ? { label: worst, gapPct: Math.round(worstGap) } : null;
    }

    function fetchNorthStarBundle() {
        var cached = readNorthStarCache();
        if (cached) return Promise.resolve(cached);
        return Promise.all([
            gatewayJson('/api/v1/risk-profile').catch(function () { return {}; }),
            gatewayJson('/api/v1/portfolio/sector-breakdown').catch(function () { return null; }),
            gatewayJson('/api/v1/recommendations/latest?page=1&page_size=1').catch(function () { return null; }),
            fetchSurplus(),
        ]).then(function (parts) {
            var risk = parts[0] || {};
            var sectorPayload = parts[1];
            var recPayload = parts[2];
            var surplus = parts[3];
            var sectors = (sectorPayload && sectorPayload.sectors) ? sectorPayload.sectors : [];
            var gap = sectorGapFromPrefs(risk.industry_preferences || [], sectors);
            var topSym = '';
            if (recPayload && recPayload.items && recPayload.items.length) {
                topSym = (recPayload.items[0].symbol || '').toUpperCase();
            }
            var inv = surplus ? parseFloat(surplus.investable_surplus || 0) : NaN;
            var data = { gap: gap, topSymbol: topSym, surplus: isFinite(inv) ? inv : null };
            writeNorthStarCache(data);
            return data;
        });
    }

    function renderNorthStarStripInvestments() {
        var strip = document.getElementById('inv-north-star-strip');
        var text = document.getElementById('inv-north-star-text');
        var link = document.getElementById('inv-north-star-link');
        if (!strip || !text) return;
        fetchNorthStarBundle().then(function (data) {
            if (!data) {
                strip.style.display = 'none';
                return;
            }
            var parts = [];
            if (isFinite(data.surplus) && data.surplus > 0) {
                parts.push('Roughly $' + Math.round(data.surplus).toLocaleString('en-US') + ' is available after bills and goals (surplus model).');
            }
            if (data.gap) {
                parts.push('A simple check suggests your largest allocation gap is ' + data.gap.label + ' (~' + data.gap.gapPct + ' points vs an even split heuristic).');
            }
            if (data.topSymbol) {
                parts.push('On your latest run, ' + data.topSymbol + ' ranks first (informational only, not a buy instruction).');
            }
            if (!parts.length) {
                strip.style.display = 'none';
                return;
            }
            text.textContent = parts.join(' ');
            if (link) {
                link.style.display = 'inline';
                link.setAttribute('href', '/recommendations');
            }
            strip.style.display = 'block';
        }).catch(function () { strip.style.display = 'none'; });
    }

    // ── Holding Detail Drawer ────────────────────────────────────────────────

    function fetchHoldingDetail(symbol) {
        return gatewayJson('/api/v1/holdings/by-symbol/' + encodeURIComponent(symbol) + '/detail')
            .catch(function () { return null; });
    }

    function openHoldingDrawer(symbol) {
        var wrap = document.getElementById('holding-detail-wrap');
        var title = document.getElementById('holding-detail-title');
        var body = document.getElementById('holding-detail-body');
        if (!wrap) return;
        if (title) title.textContent = symbol;
        if (body) body.innerHTML = '<p class="muted" style="padding:1rem 0;">Loading...</p>';
        wrap.style.display = 'block';
        wrap.setAttribute('aria-hidden', 'false');

        fetchHoldingDetail(symbol).then(function (data) {
            if (!body) return;
            if (!data) {
                body.innerHTML = '<p class="muted">Could not load details for ' + escapeHtml(symbol) + '.</p>';
                return;
            }
            var fmt = function (n) { return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
            var accountLabel = { taxable: 'Taxable', traditional_ira: 'Traditional IRA', roth_ira: 'Roth IRA', '401k': '401(k)', hsa: 'HSA', other: 'Other' };
            var html = '';
            html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">';
            html += '<div><div style="font-size:0.75rem;color:var(--text-muted);">Total quantity</div><div style="font-weight:700;">' + (data.total_quantity || 0) + '</div></div>';
            html += '<div><div style="font-size:0.75rem;color:var(--text-muted);">Avg cost</div><div style="font-weight:700;">' + fmt(data.avg_cost || 0) + '</div></div>';
            html += '<div><div style="font-size:0.75rem;color:var(--text-muted);">Total cost basis</div><div style="font-weight:700;">' + fmt(data.total_cost_basis || 0) + '</div></div>';
            html += '<div><div style="font-size:0.75rem;color:var(--text-muted);">Positions</div><div style="font-weight:700;">' + (data.positions_count || 1) + '</div></div>';
            html += '</div>';
            if (data.account_types && data.account_types.length) {
                html += '<div style="margin-bottom:0.75rem;"><span style="font-size:0.8125rem;color:var(--text-muted);">Account types: </span>';
                data.account_types.forEach(function (at) {
                    html += '<span style="display:inline-block;background:#e2e8f0;border-radius:4px;padding:1px 8px;margin-right:4px;font-size:0.8125rem;">' + escapeHtml(accountLabel[at] || at) + '</span>';
                });
                html += '</div>';
            }
            if (data.role_labels && data.role_labels.length) {
                var roleColors = { core: '#38a169', growth: '#3182ce', income: '#805ad5', hedge: '#718096', speculative: '#dd6b20' };
                html += '<div style="margin-bottom:0.75rem;"><span style="font-size:0.8125rem;color:var(--text-muted);">Role: </span>';
                data.role_labels.forEach(function (rl) {
                    var rc = roleColors[rl] || '#718096';
                    html += '<span style="display:inline-block;background:' + rc + ';color:#fff;border-radius:4px;padding:1px 8px;margin-right:4px;font-size:0.8125rem;">' + escapeHtml(rl) + '</span>';
                });
                html += '</div>';
            }
            if (data.live_quote && data.live_quote.price != null) {
                html += '<h4 style="margin:0.75rem 0 0.35rem;font-size:0.9rem;">Market</h4><ul style="font-size:0.8125rem;margin:0;padding-left:1.1rem;">';
                html += '<li>Last: ' + fmt(data.live_quote.price);
                if (data.live_quote.as_of) html += ' <span class="muted">as of ' + escapeHtml(String(data.live_quote.as_of)) + '</span>';
                html += '</li>';
                if (data.live_quote.change_pct != null) {
                    html += '<li>Day change: ' + Number(data.live_quote.change_pct).toFixed(2) + '%</li>';
                }
                if (data.live_quote.provider) {
                    html += '<li class="muted">Quote provider: ' + escapeHtml(String(data.live_quote.provider)) + '</li>';
                }
                html += '</ul>';
            }
            if (data.unrealized_pl != null && !isNaN(Number(data.unrealized_pl))) {
                html += '<p style="font-size:0.875rem;margin:0.5rem 0;"><strong>Unrealized P&amp;L</strong> (mark vs cost): ' + fmt(data.unrealized_pl) + '</p>';
            }
            if (data.tax_lots && data.tax_lots.length) {
                html += '<h4 style="margin:0.75rem 0 0.35rem;font-size:0.9rem;">Tax lots</h4>';
                html += '<table class="budget-table" style="font-size:0.75rem;"><thead><tr><th>Qty</th><th>Cost/sh</th><th>Purchased</th><th>Basis</th></tr></thead><tbody>';
                data.tax_lots.slice(0, 15).forEach(function (lot) {
                    html += '<tr><td>' + escapeHtml(String(lot.quantity)) + '</td><td>' + fmt(lot.cost_per_share) + '</td><td>' + escapeHtml(String(lot.purchase_date || '')) + '</td><td>' + fmt(lot.cost_basis) + '</td></tr>';
                });
                html += '</tbody></table>';
            }
            if (data.news_headlines && data.news_headlines.length) {
                html += '<h4 style="margin:0.75rem 0 0.35rem;font-size:0.9rem;">Recent headlines</h4><ul style="font-size:0.8125rem;padding-left:1.1rem;">';
                data.news_headlines.forEach(function (n) {
                    var t = escapeHtml(n.title || '');
                    html += '<li>' + (n.url ? '<a href="' + escapeHtml(n.url) + '" target="_blank" rel="noopener">' + t + '</a>' : t) + '</li>';
                });
                html += '</ul>';
            }
            if (data.rmd_context_flag) {
                html += '<p class="muted" style="font-size:0.78rem;margin-top:0.5rem;">You hold tax-deferred account types where RMD rules may eventually apply. This app does not compute RMD amounts—consult a tax professional.</p>';
            }
            if (data.asset_location_note) {
                html += '<p class="muted" style="font-size:0.78rem;">' + escapeHtml(data.asset_location_note) + '</p>';
            }
            if (data.valuation_fit_note) {
                html += '<p class="muted" style="font-size:0.78rem;">' + escapeHtml(data.valuation_fit_note) + '</p>';
            }
            body.innerHTML = html;
        });
    }

    function closeHoldingDrawer() {
        var wrap = document.getElementById('holding-detail-wrap');
        if (wrap) { wrap.style.display = 'none'; wrap.setAttribute('aria-hidden', 'true'); }
    }

    function initHoldingDrawer() {
        var closeBtn = document.getElementById('holding-detail-close');
        var backdrop = document.getElementById('holding-detail-backdrop');
        if (closeBtn) closeBtn.addEventListener('click', closeHoldingDrawer);
        if (backdrop) backdrop.addEventListener('click', closeHoldingDrawer);
    }

    // ── Patch form submit to include account_type ────────────────────────────

    function patchFormSubmit() {
        var form = document.getElementById('add-holding-form');
        if (!form) return;
        // We re-attach to capture account_type from the new select field
        var origSubmit = form.onsubmit;
        form.addEventListener('submit', function (e) {
            // account_type is now read in the existing handler via getElementById
            // This patch ensures the existing handler reads it
            var atEl = document.getElementById('holding-account-type');
            if (atEl && atEl.value) {
                form._pendingAccountType = atEl.value;
            }
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Run health + strip after init
    // ── Dividend Calendar ─────────────────────────────────────────────────────

    function initDividendCalendar() {
        var toggleBtn = document.getElementById('inv-dividend-toggle');
        var body = document.getElementById('inv-dividend-body');
        var list = document.getElementById('inv-dividend-list');
        if (!toggleBtn || !body) return;
        var loaded = false;
        toggleBtn.addEventListener('click', function() {
            var isHidden = body.style.display === 'none' || body.style.display === '';
            if (isHidden) {
                body.style.display = 'block';
                toggleBtn.textContent = 'Hide';
                if (!loaded) {
                    loaded = true;
                    gatewayJson('/api/v1/holdings').then(function(data) {
                        var items = (data && data.items) || [];
                        if (!items.length) { if (list) list.innerHTML = '<p class="muted">Add holdings to see dividend information.</p>'; return; }
                        var rows = items.filter(function(h) { return h.symbol; });
                        var html = '<ul style="list-style:none;padding:0;margin:0;">';
                        rows.forEach(function(h) {
                            html += '<li style="padding:0.4rem 0;border-bottom:1px solid var(--border);font-size:0.875rem;">';
                            html += '<strong>' + escapeHtml(h.symbol || '') + '</strong>';
                            html += '<span class="muted" style="margin-left:0.5rem;">Dividend yield data available via market data providers when configured.</span>';
                            html += '</li>';
                        });
                        html += '</ul>';
                        html += '<p style="font-size:0.75rem;color:var(--text-muted);margin-top:0.5rem;">Dividend amounts and dates are estimates based on historical data. Companies may change or cancel dividends at any time.</p>';
                        if (list) list.innerHTML = html;
                    }).catch(function() {
                        if (list) list.innerHTML = '<p class="muted">Could not load dividend data.</p>';
                    });
                }
            } else {
                body.style.display = 'none';
                toggleBtn.textContent = 'Show';
            }
        });
    }

    // ── Cash Opportunity Cost Strip ───────────────────────────────────────────

    function checkCashOpportunity() {
        var strip = document.getElementById('inv-cash-strip');
        var text = document.getElementById('inv-cash-strip-text');
        if (!strip || !text) return;
        fetchSurplus().then(function(data) {
            if (!data) return;
            var surplus = parseFloat(data.investable_surplus || 0);
            if (surplus > 500) {
                var hysa_low = (surplus * 0.04).toFixed(0);
                var hysa_high = (surplus * 0.05).toFixed(0);
                text.textContent = 'Your estimated available amount of $' + Math.round(surplus).toLocaleString() +
                    ' could earn approximately $' + hysa_low + '\u2013$' + hysa_high +
                    '/year in a high-yield savings account (vs. a typical bank rate). This is informational \u2014 actual rates vary.';
                strip.style.display = 'block';
            }
        });
    }

    // ── CSV Import ──────────────────────────────────────────
    function initCsvImport() {
        var openBtn = document.getElementById('import-csv-open-btn');
        var modal = document.getElementById('import-csv-modal');
        var closeBtn = document.getElementById('import-csv-close');
        var cancelBtn = document.getElementById('import-csv-cancel');
        var submitBtn = document.getElementById('import-csv-submit');
        var fileInput = document.getElementById('import-csv-file');
        var brokerSelect = document.getElementById('import-broker-select');
        var feedback = document.getElementById('import-csv-feedback');

        if (!modal) return;

        function openModal() { modal.classList.remove('hidden'); modal.removeAttribute('aria-hidden'); }
        function closeModal() { modal.classList.add('hidden'); modal.setAttribute('aria-hidden', 'true'); if (fileInput) fileInput.value = ''; if (feedback) feedback.style.display = 'none'; }

        if (openBtn) openBtn.addEventListener('click', openModal);
        if (closeBtn) closeBtn.addEventListener('click', closeModal);
        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });

        function showFeedback(msg, type) {
            if (!feedback) return;
            feedback.textContent = msg;
            feedback.style.display = 'block';
            feedback.style.background = type === 'success' ? 'var(--green-bg,#ecfdf5)' : 'var(--red-bg,#fef2f2)';
            feedback.style.color = type === 'success' ? 'var(--green-text,#065f46)' : 'var(--red-text,#991b1b)';
        }

        if (submitBtn) {
            submitBtn.addEventListener('click', function() {
                if (!fileInput || !fileInput.files[0]) {
                    showFeedback('Please select a CSV file.', 'error'); return;
                }
                submitBtn.disabled = true;
                submitBtn.textContent = 'Importing\u2026';
                var formData = new FormData();
                formData.append('file', fileInput.files[0]);
                if (brokerSelect && brokerSelect.value) formData.append('broker', brokerSelect.value);
                var token = localStorage.getItem('authToken') || (window.Auth && window.Auth.getToken && window.Auth.getToken()) || '';
                fetch((window.API_BASE || '') + '/api/v1/holdings/import-csv', {
                    method: 'POST',
                    headers: token ? { 'Authorization': 'Bearer ' + token } : {},
                    body: formData,
                }).then(function(res) {
                    return res.json().then(function(data) { return { ok: res.ok, data: data }; });
                }).then(function(result) {
                    if (result.ok) {
                        showFeedback('Imported ' + (result.data.imported || 0) + ' holdings successfully.', 'success');
                        setTimeout(function() { closeModal(); if (typeof fetchHoldings === 'function') fetchHoldings(); }, 1500);
                    } else {
                        showFeedback((result.data && result.data.detail) || 'Import failed. Check your CSV format.', 'error');
                    }
                }).catch(function() {
                    showFeedback('Network error. Please try again.', 'error');
                }).finally(function() {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Import';
                });
            });
        }
    }

    // ── Benchmark Chart ──────────────────────────────────────
    function fetchBenchmarkData(benchmark, days) {
        var token = localStorage.getItem('authToken') || (window.Auth && window.Auth.getToken && window.Auth.getToken()) || '';
        return fetch((window.API_BASE || '') + '/api/v1/portfolio/benchmark?benchmark=' + encodeURIComponent(benchmark) + '&days=' + encodeURIComponent(days), {
            headers: token ? { 'Authorization': 'Bearer ' + token } : {},
        }).then(function(res) {
            if (!res.ok) return null;
            return res.json();
        }).catch(function() { return null; });
    }

    function renderBenchmarkChart(data) {
        var canvas = document.getElementById('benchmark-chart');
        var alphaEl = document.getElementById('benchmark-alpha');
        if (!canvas || !data) return;
        var ctx = canvas.getContext('2d');
        if (!ctx) return;

        if (canvas._chartInstance) { canvas._chartInstance.destroy(); }

        var portfolioPoints = data.portfolio_points || [];
        var benchmarkSeries = data.benchmark_series || [];
        var labels = portfolioPoints.map(function(_, i) {
            return i === 0 ? 'Start' : (i === portfolioPoints.length - 1 ? 'Now' : '');
        });

        if (typeof Chart === 'undefined') {
            var wrap = document.getElementById('benchmark-chart-wrap');
            if (wrap) wrap.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-secondary)">Chart.js required for benchmark chart.</div>';
            return;
        }

        canvas._chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Your Portfolio',
                        data: portfolioPoints,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.08)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true,
                    },
                    {
                        label: data.benchmark_label || 'Benchmark',
                        data: benchmarkSeries,
                        borderColor: '#94a3b8',
                        borderWidth: 1.5,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        tension: 0.3,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { font: { size: 12 } } },
                    tooltip: {
                        callbacks: {
                            label: function(c) { return c.dataset.label + ': ' + (c.parsed.y >= 0 ? '+' : '') + c.parsed.y.toFixed(2) + '%'; },
                        },
                    },
                },
                scales: {
                    y: {
                        ticks: {
                            callback: function(v) { return (v >= 0 ? '+' : '') + v.toFixed(1) + '%'; },
                            font: { size: 11 },
                        },
                        grid: { color: 'rgba(0,0,0,0.05)' },
                    },
                    x: { display: false },
                },
            },
        });

        if (alphaEl && data.alpha_pct != null) {
            var alpha = parseFloat(data.alpha_pct);
            alphaEl.textContent = 'Alpha vs ' + (data.benchmark_label || 'benchmark') + ': ' + (alpha >= 0 ? '+' : '') + alpha.toFixed(2) + '%';
            alphaEl.style.color = alpha >= 0 ? 'var(--green-text,#065f46)' : 'var(--red-text,#991b1b)';
        }
    }

    function loadBenchmark() {
        var benchmarkSelect = document.getElementById('benchmark-select');
        var daysSelect = document.getElementById('benchmark-days');
        var loading = document.getElementById('benchmark-loading');
        var chartWrap = document.getElementById('benchmark-chart-wrap');
        if (!benchmarkSelect) return;
        var benchmark = benchmarkSelect.value || 'sp500';
        var days = daysSelect ? daysSelect.value : '90';
        if (loading) loading.style.display = 'block';
        if (chartWrap) chartWrap.style.opacity = '0.4';
        fetchBenchmarkData(benchmark, days).then(function(data) {
            if (loading) loading.style.display = 'none';
            if (chartWrap) chartWrap.style.opacity = '1';
            if (data) renderBenchmarkChart(data);
        });
    }

    function initBenchmarkChart() {
        var refreshBtn = document.getElementById('benchmark-refresh-btn');
        var benchmarkSelect = document.getElementById('benchmark-select');
        var daysSelect = document.getElementById('benchmark-days');
        if (refreshBtn) refreshBtn.addEventListener('click', loadBenchmark);
        if (benchmarkSelect) benchmarkSelect.addEventListener('change', loadBenchmark);
        if (daysSelect) daysSelect.addEventListener('change', loadBenchmark);
        loadBenchmark();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            fetchPortfolioHealth().then(renderHealthScore);
            fetchSurplus().then(renderFinanceStrip);
            renderNorthStarStripInvestments();
            initHoldingDrawer();
            patchFormSubmit();
            initDividendCalendar();
            checkCashOpportunity();
            initCsvImport();
            initBenchmarkChart();
        });
    } else {
        fetchPortfolioHealth().then(renderHealthScore);
        fetchSurplus().then(renderFinanceStrip);
        renderNorthStarStripInvestments();
        initHoldingDrawer();
        patchFormSubmit();
        initDividendCalendar();
        checkCashOpportunity();
        initCsvImport();
        initBenchmarkChart();
    }

    window.Investments = {
        fetchHoldings: fetchHoldings,
        renderHoldings: renderHoldings,
        sellHolding: sellHolding,
        openHoldingDrawer: openHoldingDrawer,
    };
})();
