(function () {
    'use strict';

    var API = window.API_BASE || '';

    function getAuthHeaders() {
        if (window.Auth && window.Auth.getAuthHeaders) {
            return window.Auth.getAuthHeaders();
        }
        var token = window.Auth && window.Auth.getAccessToken && window.Auth.getAccessToken();
        if (!token) return {};
        return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
    }

    function runRecommendations() {
        var headers = getAuthHeaders();
        headers['Content-Type'] = 'application/json';
        return fetch(API + '/api/v1/recommendations/run', {
            method: 'POST',
            headers: headers,
            body: '{}'
        }).then(function (r) {
            if (!r.ok) {
                return r.json().catch(function () { return {}; }).then(function (body) {
                    throw new Error(body.detail || 'Failed to run recommendations');
                });
            }
            return r.json();
        });
    }

    function fetchLatest() {
        return fetch(API + '/api/v1/recommendations/latest', {
            headers: getAuthHeaders()
        }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load latest recommendations');
            return r.json();
        });
    }

    function fetchExplain(runId) {
        return fetch(API + '/api/v1/recommendations/' + encodeURIComponent(runId) + '/explain', {
            headers: getAuthHeaders()
        }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load explanation');
            return r.json();
        });
    }

    function formatPct(x) {
        var n = Number(x);
        if (!isFinite(n)) return '—';
        return (n * 100).toFixed(0) + '%';
    }

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function renderSummary(summaryEl, data) {
        if (!summaryEl) return;
        if (!data || !data.portfolio) {
            summaryEl.textContent = 'No recommendation run yet.';
            return;
        }
        var p = data.portfolio;
        var html = '<ul class="portfolio-metrics">';
        html += '<li><strong>Total value</strong>: $' + escapeHtml(p.total_value) + '</li>';
        html += '<li><strong>Total cost basis</strong>: $' + escapeHtml(p.total_cost_basis) + '</li>';
        html += '<li><strong>Unrealized P/L</strong>: $' + escapeHtml(p.unrealized_pl) + '</li>';
        html += '<li><strong>Realized P/L</strong>: $' + escapeHtml(p.realized_pl) + '</li>';
        html += '<li><strong>Sharpe ratio</strong>: ' + escapeHtml(p.sharpe) + '</li>';
        html += '<li><strong>Volatility (annual)</strong>: ' + escapeHtml(p.volatility_annual) + '</li>';
        html += '<li><strong>Max drawdown</strong>: ' + escapeHtml(p.max_drawdown) + '</li>';
        html += '<li><strong>Top position weight</strong>: ' + escapeHtml(p.top1_weight) + '</li>';
        html += '</ul>';
        summaryEl.innerHTML = html;
    }

    function renderList(listEl, statusEl, payload) {
        if (!listEl || !statusEl) return;
        var run = payload && payload.run;
        var items = payload && payload.items || [];
        if (!run || !items.length) {
            statusEl.textContent = 'No recommendations yet. Click “Generate recommendations” to run the engine.';
            listEl.innerHTML = '';
            return;
        }
        statusEl.textContent = 'Latest run at ' + (run.created_at || '—');
        var html = '<ul class="recommendation-items">';
        items.forEach(function (it, idx) {
            var sym = (it.symbol || '').toUpperCase();
            html += '<li class="recommendation-item" data-index="' + idx + '">';
            html += '<div class="rec-symbol">' + escapeHtml(sym) + '</div>';
            html += '<div class="rec-meta">';
            html += '<span class="rec-score">Score: ' + escapeHtml(String(it.score)) + '</span>';
            html += '<span class="rec-confidence">Confidence: ' + escapeHtml(formatPct(it.confidence)) + '</span>';
            html += '</div>';
            html += '<button type="button" class="btn btn-secondary btn-sm rec-explain-btn" data-symbol="' + escapeHtml(sym) + '">View details</button>';
            html += '</li>';
        });
        listEl.innerHTML = html;
        listEl.setAttribute('data-run-id', run.run_id || '');
    }

    function openExplainDrawer(rootEl, runId, symbol) {
        var wrap = document.getElementById('rec-explain-wrap');
        if (!wrap || !runId) return;
        var bodyEl = document.getElementById('rec-explain-body');
        var titleEl = document.getElementById('rec-explain-title');
        if (titleEl) titleEl.textContent = 'Why ' + symbol + '?';
        bodyEl.innerHTML = '<p class="muted">Loading details…</p>';
        wrap.style.display = 'block';
        wrap.setAttribute('aria-hidden', 'false');

        fetchExplain(runId).then(function (data) {
            var items = data && data.items || [];
            var match = null;
            items.forEach(function (it) {
                if ((it.symbol || '').toUpperCase() === symbol.toUpperCase()) {
                    match = it;
                }
            });
            if (!match || !match.explanation) {
                bodyEl.innerHTML = '<p class="muted">No explanation available.</p>';
                return;
            }
            var ex = match.explanation;
            var html = '';
            if (ex.why_selected && ex.why_selected.length) {
                html += '<h4>Why selected</h4><ul>';
                ex.why_selected.forEach(function (s) {
                    html += '<li>' + escapeHtml(String(s)) + '</li>';
                });
                html += '</ul>';
            }
            if (ex.risk_metrics) {
                html += '<h4>Risk & return</h4><ul>';
                html += '<li><strong>Sharpe</strong>: ' + escapeHtml(String(ex.risk_metrics.sharpe)) + '</li>';
                html += '<li><strong>Volatility (annual)</strong>: ' + escapeHtml(String(ex.risk_metrics.volatility_annual)) + '</li>';
                html += '<li><strong>Max drawdown</strong>: ' + escapeHtml(String(ex.risk_metrics.max_drawdown)) + '</li>';
                html += '</ul>';
            }
            if (ex.data_freshness) {
                html += '<h4>Data freshness</h4><ul>';
                if (ex.data_freshness.provider) {
                    html += '<li><strong>Provider</strong>: ' + escapeHtml(String(ex.data_freshness.provider)) + '</li>';
                }
                if (ex.data_freshness.stale_seconds != null) {
                    html += '<li><strong>Stale (seconds)</strong>: ' + escapeHtml(String(ex.data_freshness.stale_seconds)) + '</li>';
                }
                html += '</ul>';
            }
            if (ex.confidence) {
                html += '<h4>Confidence</h4><p>Confidence index: ' + formatPct(ex.confidence.value) + '</p>';
            }
            if (ex.news_factors) {
                html += '<h4>News & events</h4>';
                if (ex.news_factors.event_flags && ex.news_factors.event_flags.length) {
                    html += '<p>Events: ' + escapeHtml(ex.news_factors.event_flags.join(', ')) + '</p>';
                } else {
                    html += '<p class="muted">No specific news factors recorded.</p>';
                }
            }
            bodyEl.innerHTML = html;
        }).catch(function () {
            bodyEl.innerHTML = '<p class="muted">Failed to load explanation.</p>';
        });
    }

    function closeExplainDrawer() {
        var wrap = document.getElementById('rec-explain-wrap');
        if (!wrap) return;
        wrap.style.display = 'none';
        wrap.setAttribute('aria-hidden', 'true');
    }

    function init() {
        var listEl = document.getElementById('rec-list');
        var statusEl = document.getElementById('rec-status');
        var summaryEl = document.getElementById('rec-portfolio-summary');
        if (!listEl || !statusEl) return;

        fetchLatest().then(function (data) {
            renderList(listEl, statusEl, data);
        }).catch(function () {
            statusEl.textContent = 'Could not load latest recommendations. Make sure you are logged in.';
        });

        var runBtn = document.getElementById('rec-run-btn');
        if (runBtn) {
            runBtn.addEventListener('click', function () {
                statusEl.textContent = 'Generating recommendations…';
                runBtn.disabled = true;
                runRecommendations().then(function (data) {
                    renderList(listEl, statusEl, data);
                    renderSummary(summaryEl, data);
                }).catch(function (err) {
                    alert(err.message || 'Failed to run recommendations');
                }).finally(function () {
                    runBtn.disabled = false;
                });
            });
        }

        listEl.addEventListener('click', function (e) {
            var btn = e.target.closest('.rec-explain-btn');
            if (!btn) return;
            var symbol = btn.getAttribute('data-symbol') || '';
            var runId = listEl.getAttribute('data-run-id') || '';
            openExplainDrawer(listEl, runId, symbol);
        });

        var closeBtn = document.getElementById('rec-explain-close');
        if (closeBtn) closeBtn.addEventListener('click', closeExplainDrawer);
        var backdrop = document.getElementById('rec-explain-backdrop');
        if (backdrop) backdrop.addEventListener('click', closeExplainDrawer);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

