(function () {
    'use strict';

    var API = window.API_BASE || '';

    function apiErrorDetail(body) {
        if (!body) return 'Request failed';
        var d = body.detail;
        if (typeof d === 'string') return d;
        if (Array.isArray(d) && d.length) {
            return d.map(function (e) {
                var loc = (e.loc && e.loc.slice(1).join('.')) || '';
                return (loc ? loc + ': ' : '') + (e.msg || e.message || '');
            }).join('; ');
        }
        return body.detail ? String(body.detail) : 'Request failed';
    }

    function getAuthHeaders() {
        if (window.Auth && window.Auth.getAuthHeaders) {
            return window.Auth.getAuthHeaders();
        }
        var token = window.Auth && window.Auth.getToken && window.Auth.getToken();
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
                    throw new Error(apiErrorDetail(body) || 'Failed to run recommendations');
                });
            }
            return r.json();
        });
    }

    var PAGE_SIZE = 20;

    function fetchLatest(page, enrich) {
        page = page || 1;
        var url = API + '/api/v1/recommendations/latest?page=' + page + '&page_size=' + PAGE_SIZE;
        if (enrich) url += '&enrich=1';
        return fetch(url, { headers: getAuthHeaders() }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load latest recommendations');
            return r.json();
        });
    }

    function fetchExplain(runId, symbol) {
        var url = API + '/api/v1/recommendations/' + encodeURIComponent(runId) + '/explain';
        if (symbol) url += '?symbol=' + encodeURIComponent(symbol);
        return fetch(url, { headers: getAuthHeaders() }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load explanation');
            return r.json();
        });
    }

    function fetchRiskProfile() {
        return fetch(API + '/api/v1/risk-profile', { headers: getAuthHeaders() }).then(function (r) {
            if (!r.ok) return null;
            return r.json();
        }).catch(function () { return null; });
    }

    function saveRiskProfile(payload) {
        var headers = getAuthHeaders();
        headers['Content-Type'] = 'application/json';
        var body = {};
        if (payload.risk_tolerance != null) body.risk_tolerance = payload.risk_tolerance;
        if (payload.industry_preferences != null) body.industry_preferences = payload.industry_preferences;
        if (payload.sharpe_objective != null) body.sharpe_objective = payload.sharpe_objective;
        if (payload.loss_aversion != null) body.loss_aversion = payload.loss_aversion;
        if (payload.use_finance_data_for_recommendations != null) body.use_finance_data_for_recommendations = !!payload.use_finance_data_for_recommendations;
        return fetch(API + '/api/v1/risk-profile', {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify(body)
        }).then(function (r) {
            if (!r.ok) return r.json().catch(function () { return {}; }).then(function (b) {
                throw new Error(apiErrorDetail(b) || 'Failed to save preferences');
            });
            return r.json();
        });
    }

    function formatPct(x) {
        var n = Number(x);
        if (!isFinite(n)) return '—';
        return (n * 100).toFixed(2) + '%';
    }

    function formatNum2(x) {
        var n = Number(x);
        if (!isFinite(n)) return '—';
        return n.toFixed(2);
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
            summaryEl.innerHTML = '<p class="muted">Run recommendations above to see portfolio risk metrics (Sharpe, volatility, drawdown). Add holdings on the <a href="/investments">Investments</a> page first for meaningful numbers.</p>';
            return;
        }
        var p = data.portfolio;
        var html = '<ul class="portfolio-metrics">';
        html += '<li><strong>Total value</strong>: $' + escapeHtml(formatNum2(p.total_value)) + '</li>';
        html += '<li><strong>Total cost basis</strong>: $' + escapeHtml(formatNum2(p.total_cost_basis)) + '</li>';
        html += '<li><strong>Unrealized P/L</strong>: $' + escapeHtml(formatNum2(p.unrealized_pl)) + '</li>';
        html += '<li><strong>Realized P/L</strong>: $' + escapeHtml(formatNum2(p.realized_pl)) + '</li>';
        html += '<li><strong>Sharpe ratio</strong>: ' + escapeHtml(formatNum2(p.sharpe)) + '</li>';
        html += '<li><strong>Volatility (annual)</strong>: ' + escapeHtml(formatNum2(p.volatility_annual)) + '</li>';
        html += '<li><strong>Max drawdown</strong>: ' + escapeHtml(formatNum2(p.max_drawdown)) + '</li>';
        html += '<li><strong>Top position weight</strong>: ' + escapeHtml(formatNum2(p.top1_weight)) + '</li>';
        if (p.top3_weight != null && p.top3_weight !== '') {
            html += '<li><strong>Top 3 weight</strong>: ' + escapeHtml(formatNum2(p.top3_weight)) + '</li>';
        }
        if (p.hhi != null && p.hhi !== '') {
            html += '<li><strong>Concentration (HHI)</strong>: ' + escapeHtml(formatNum2(p.hhi)) + '</li>';
        }
        if (p.position_count != null && p.position_count !== '') {
            html += '<li><strong>Positions</strong>: ' + escapeHtml(String(p.position_count)) + '</li>';
        }
        if (p.snapshot_date) {
            html += '<li><strong>Snapshot as of</strong>: ' + escapeHtml(String(p.snapshot_date)) + '</li>';
        }
        html += '</ul>';
        if (p.holdings_top && p.holdings_top.length) {
            html += '<h4 style="margin:1rem 0 0.5rem;font-size:0.95rem;">Largest positions</h4><ul class="portfolio-holdings-top" style="font-size:0.875rem;padding-left:1.1rem;">';
            p.holdings_top.slice(0, 8).forEach(function (h) {
                html += '<li><strong>' + escapeHtml(h.symbol || '—') + '</strong> — weight ' + escapeHtml(formatNum2(h.weight))
                    + (h.source ? ' · ' + escapeHtml(h.source) : '') + '</li>';
            });
            html += '</ul>';
        }
        summaryEl.innerHTML = html;
    }

    function renderList(listEl, statusEl, payload, currentPage) {
        if (!listEl || !statusEl) return;
        var run = payload && payload.run;
        var items = payload && payload.items || [];
        var pagination = payload && payload.pagination || {};
        var totalPages = pagination.total_pages || 1;
        var totalItems = pagination.total_items || 0;
        currentPage = currentPage != null ? currentPage : (pagination.page || 1);
        if (!run) {
            statusEl.textContent = 'Click “Generate recommendations” to get a starter list (no holdings needed) or to rank your current holdings. Save your preferences above first for best results.';
            listEl.innerHTML = '<p class="muted">Generate recommendations to see analyst suggestions. With no holdings you get a starter portfolio; with holdings you get ranked positions and risk notes.</p><div id="rec-pagination" class="rec-pagination"></div>';
            if (listEl.setAttribute) listEl.setAttribute('data-run-id', '');
            return;
        }
        statusEl.textContent = 'Latest run at ' + (run.created_at || '—');
        var html = '<div class="rec-table-wrap"><table class="rec-table"><thead><tr>';
        html += '<th>Symbol</th><th>Name</th><th>Sector</th><th>Score <span class="rec-score-hint" title="Click score to see how it was calculated">(?)</span></th><th>Conf.</th><th>Last price</th><th>Change %</th><th>1M trend</th><th>Actions</th></tr></thead><tbody>';
        if (!items.length) {
            html += '<tr><td colspan="9" class="muted">No items on this page.</td></tr>';
        } else {
        items.forEach(function (it, idx) {
            var sym = (it.symbol || '').toUpperCase();
            var name = it.full_name || it.description || '—';
            var sector = it.sector || '—';
            var lastPrice = it.last_price != null ? '$' + escapeHtml(formatNum2(it.last_price)) : '—';
            var changePct = it.change_pct != null ? (Number(it.change_pct) >= 0 ? '+' : '') + Number(it.change_pct).toFixed(2) + '%' : '—';
            var trend1m = it.trend_1m_pct != null ? (Number(it.trend_1m_pct) >= 0 ? '+' : '') + Number(it.trend_1m_pct).toFixed(2) + '%' : '—';
            var scoreStr = formatNum2(it.score);
            html += '<tr class="recommendation-item" data-index="' + idx + '">';
            html += '<td class="rec-symbol">' + escapeHtml(sym) + '</td>';
            html += '<td class="rec-name">' + escapeHtml(name) + '</td>';
            html += '<td class="rec-sector">' + escapeHtml(sector) + '</td>';
            html += '<td class="rec-score"><button type="button" class="rec-score-btn" data-symbol="' + escapeHtml(sym) + '" title="How was this score determined?">' + escapeHtml(scoreStr) + '</button></td>';
            html += '<td class="rec-confidence">' + escapeHtml(formatPct(it.confidence)) + '</td>';
            html += '<td class="rec-last-price">' + lastPrice + '</td>';
            html += '<td class="rec-change-pct">' + escapeHtml(changePct) + '</td>';
            html += '<td class="rec-trend-1m">' + escapeHtml(trend1m) + '</td>';
            html += '<td class="rec-actions">';
            html += '<button type="button" class="btn btn-secondary btn-sm rec-explain-btn" data-symbol="' + escapeHtml(sym) + '">View details</button>';
            html += ' <a href="/investments?add=' + encodeURIComponent(sym) + '" class="btn btn-sm btn-ghost rec-add-holding" data-symbol="' + escapeHtml(sym) + '">Add to holdings</a>';
            html += '</td></tr>';
        });
        }
        html += '</tbody></table></div>';
        html += '<div id="rec-pagination" class="rec-pagination">';
        if (totalItems > 0) {
            html += '<span class="rec-pagination-info">Page ' + currentPage + ' of ' + totalPages + ' (' + totalItems + ' total)</span>';
            if (currentPage > 1) {
                html += ' <button type="button" class="btn btn-sm rec-pagination-prev" data-page="' + (currentPage - 1) + '">Prev</button>';
            }
            if (currentPage < totalPages) {
                html += ' <button type="button" class="btn btn-sm rec-pagination-next" data-page="' + (currentPage + 1) + '">Next</button>';
            }
        }
        html += '</div>';
        listEl.innerHTML = html;
        listEl.setAttribute('data-run-id', run.run_id || '');
        listEl.setAttribute('data-current-page', String(currentPage));
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

        fetchExplain(runId, symbol).then(function (data) {
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
            if (!ex || typeof ex !== 'object') ex = {};
            // Robust defaults so the drawer can render placeholders even when the backend returns partial data.
            if (!ex.data_freshness) ex.data_freshness = { provider: 'Unavailable', stale_seconds: null };
            if (!ex.market) ex.market = {};
            if (!ex.enrichment) ex.enrichment = {};
            if (!ex.sentiment_trend_7d) ex.sentiment_trend_7d = { daily_scores: [], rolling_avg_7d: null };
            if (!ex.news_factors) ex.news_factors = { recent_news: [] };
            if (!ex.news_provider_status) ex.news_provider_status = { provider_order: [], configured_keys: {}, message: 'No diagnostics returned by backend' };
            var html = '';
            if (ex.personalized_with_finance_data) {
                html += '<p class="muted" style="font-size:0.85rem; margin-bottom:1rem;">Personalized using your savings, goals, and budget data.</p>';
            }
            if (ex.security) {
                var sec = ex.security;
                html += '<h4>Security</h4><ul>';
                html += '<li><strong>Name</strong>: ' + escapeHtml(sec.full_name || '—') + '</li>';
                html += '<li><strong>Sector</strong>: ' + escapeHtml(sec.sector || '—') + '</li>';
                html += '<li><strong>Asset type</strong>: ' + escapeHtml(sec.asset_type || '—') + '</li>';
                if (sec.why_it_matters) {
                    html += '<li><strong>Why it matters</strong>: ' + escapeHtml(String(sec.why_it_matters)) + '</li>';
                }
                html += '</ul>';
            }
            if (ex.market) {
                var m = ex.market;
                html += '<h4>Market</h4><ul>';
                html += '<li><strong>Current price</strong>: $' + escapeHtml(m.current_price != null ? formatNum2(m.current_price) : '—') + '</li>';
                if (m.as_of) html += '<li><strong>As of</strong>: ' + escapeHtml(String(m.as_of)) + '</li>';
                if (m.trend_1m_pct != null) html += '<li><strong>1M trend</strong>: ' + escapeHtml(Number(m.trend_1m_pct).toFixed(2)) + '%</li>';
                if (m['52w_high'] != null) html += '<li><strong>52w high</strong>: $' + escapeHtml(formatNum2(m['52w_high'])) + '</li>';
                if (m['52w_low'] != null) html += '<li><strong>52w low</strong>: $' + escapeHtml(formatNum2(m['52w_low'])) + '</li>';
                html += '</ul>';
            }
            if (ex.enrichment) {
                var en = ex.enrichment;
                html += '<h4>Enrichment</h4><ul>';
                if (en.quote) {
                    html += '<li><strong>Live price</strong>: $' + escapeHtml(en.quote.price != null ? formatNum2(en.quote.price) : '—') + '</li>';
                    if (en.quote.as_of) html += '<li><strong>As of</strong>: ' + escapeHtml(String(en.quote.as_of)) + '</li>';
                    if (en.quote.change_pct != null) html += '<li><strong>Day change</strong>: ' + escapeHtml(Number(en.quote.change_pct).toFixed(2)) + '%</li>';
                }
                if (en.trend_1m_pct != null) html += '<li><strong>1M trend</strong>: ' + escapeHtml(Number(en.trend_1m_pct).toFixed(2)) + '%</li>';
                if (en['52w_high'] != null) html += '<li><strong>52w high</strong>: $' + escapeHtml(formatNum2(en['52w_high'])) + '</li>';
                if (en['52w_low'] != null) html += '<li><strong>52w low</strong>: $' + escapeHtml(formatNum2(en['52w_low'])) + '</li>';
                if (en.data_freshness && en.data_freshness.provider) html += '<li><strong>Provider</strong>: ' + escapeHtml(String(en.data_freshness.provider)) + '</li>';
                html += '</ul>';
                if (en.recent_news && en.recent_news.length) {
                    html += '<p class="rec-enrichment-news"><strong>Recent news</strong> <span class="muted">(provider tags where available)</span></p><ul class="rec-news-list">';
                    en.recent_news.forEach(function (n) {
                        var title = (n.title || 'Headline').substring(0, 80);
                        if ((n.title || '').length > 80) title += '…';
                        var link = n.url ? '<a href="' + escapeHtml(n.url) + '" target="_blank" rel="noopener">' + escapeHtml(title) + '</a>' : escapeHtml(title);
                        var prov = n.source_provider ? ' <span class="muted">[' + escapeHtml(String(n.source_provider)) + ']</span>' : '';
                        html += '<li>' + link + prov + (n.published_at ? ' <span class="muted">' + escapeHtml(String(n.published_at)) + '</span>' : '') + '</li>';
                    });
                    html += '</ul>';
                }
            }
            html += '<h4>Market sentiment</h4>';
            if (ex.sentiment_summary) {
                html += '<p>' + escapeHtml(String(ex.sentiment_summary)) + '</p>';
                if (ex.sentiment_context) {
                    html += '<p class="muted" style="font-size:0.8rem;">Source: ' + escapeHtml(String(ex.sentiment_context)) + '</p>';
                }
                if (ex.sentiment_trend_7d && ex.sentiment_trend_7d.daily_scores && ex.sentiment_trend_7d.daily_scores.length) {
                    html += '<p class="muted" style="font-size:0.85rem;">7-day rolling average (stored scores): ' + (ex.sentiment_trend_7d.rolling_avg_7d != null ? escapeHtml(Number(ex.sentiment_trend_7d.rolling_avg_7d).toFixed(2)) : '—') + '</p>';
                }
            } else if (ex.sentiment_trend_7d && ex.sentiment_trend_7d.daily_scores && ex.sentiment_trend_7d.daily_scores.length) {
                html += '<p class="muted">Summarizing from trend…</p>';
            } else {
                html += '<p class="muted">No 7-day sentiment series returned; see News &amp; events for headline context (Benzinga / Finnhub / other configured feeds).</p>';
            }
            if (ex.why_selected_evidence && ex.why_selected_evidence.length) {
                html += '<h4>Why this appeared in your list (data &amp; settings)</h4><ul class="rec-evidence-list">';
                ex.why_selected_evidence.forEach(function (row) {
                    var src = row.source || 'Input';
                    var det = row.detail || '';
                    html += '<li><strong>' + escapeHtml(String(src)) + '</strong>: ' + escapeHtml(String(det)) + '</li>';
                });
                html += '</ul>';
            } else if (ex.why_selected && ex.why_selected.length) {
                html += '<h4>Why this appeared in your list</h4><ul>';
                ex.why_selected.forEach(function (s) {
                    html += '<li>' + escapeHtml(String(s)) + '</li>';
                });
                html += '</ul>';
            }
            if (ex.risk_return_narrative && ex.risk_return_narrative.length) {
                html += '<h4>Risk &amp; return (how we use these metrics)</h4><ul>';
                ex.risk_return_narrative.forEach(function (line) {
                    html += '<li>' + escapeHtml(String(line)) + '</li>';
                });
                html += '</ul>';
            }
            if (ex.risk_metrics) {
                var rm = ex.risk_metrics;
                var sharpeStr = rm.sharpe != null && String(rm.sharpe).indexOf('N/A') === -1 ? formatNum2(rm.sharpe) : (rm.sharpe != null ? String(rm.sharpe) : '—');
                var volStr = rm.volatility_annual != null && String(rm.volatility_annual).indexOf('N/A') === -1 ? formatNum2(rm.volatility_annual) : (rm.volatility_annual != null ? String(rm.volatility_annual) : '—');
                var mddStr = rm.max_drawdown != null && String(rm.max_drawdown).indexOf('N/A') === -1 ? formatNum2(rm.max_drawdown) : (rm.max_drawdown != null ? String(rm.max_drawdown) : '—');
                html += '<h4>Risk &amp; return (numbers)</h4><ul>';
                html += '<li><strong>Sharpe</strong>: ' + escapeHtml(sharpeStr) + '</li>';
                html += '<li><strong>Volatility (annual)</strong>: ' + escapeHtml(volStr) + '</li>';
                html += '<li><strong>Max drawdown</strong>: ' + escapeHtml(mddStr) + '</li>';
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
            if (ex.analyst_note_detail || ex.analyst_note) {
                html += '<h4>Analyst-style note</h4><p style="white-space:pre-wrap;">' + escapeHtml(String(ex.analyst_note_detail || ex.analyst_note)) + '</p>';
            }
            if (ex.narrative) {
                html += '<h4>Summary</h4><p>' + escapeHtml(String(ex.narrative)) + '</p>';
            }
            if (ex.news_factors) {
                html += '<h4>News &amp; events</h4>';
                if (ex.news_factors.recent_news && ex.news_factors.recent_news.length) {
                    html += '<ul class="rec-news-list">';
                    ex.news_factors.recent_news.forEach(function (n) {
                        var title = (n.title || 'Headline').substring(0, 80);
                        if ((n.title || '').length > 80) title += '…';
                        var link = n.url ? '<a href="' + escapeHtml(n.url) + '" target="_blank" rel="noopener">' + escapeHtml(title) + '</a>' : escapeHtml(title);
                        var prov = n.source_provider ? ' <span class="muted">[' + escapeHtml(String(n.source_provider)) + ']</span>' : '';
                        html += '<li>' + link + prov + (n.published_at ? ' <span class="muted">' + escapeHtml(String(n.published_at)) + '</span>' : '') + '</li>';
                    });
                    html += '</ul>';
                } else if (ex.news_factors.event_flags && ex.news_factors.event_flags.length) {
                    html += '<p>Events: ' + escapeHtml(ex.news_factors.event_flags.join(', ')) + '</p>';
                } else {
                    html += '<p class="muted">No headlines returned for this symbol in the current window. Check Benzinga / Finnhub / Alpha Vantage / Twelve Data keys in environment.</p>';
                }
            }
            if (ex.news_provider_status) {
                var nps = ex.news_provider_status;
                html += '<p class="muted" style="font-size:0.8rem;">';
                html += 'Provider diagnostics: ';
                if (nps.provider_order && nps.provider_order.length) {
                    html += 'order=' + escapeHtml(String(nps.provider_order.join(','))) + '; ';
                }
                if (nps.configured_keys) {
                    var cfg = [];
                    Object.keys(nps.configured_keys).forEach(function (k) {
                        cfg.push(k + '=' + (nps.configured_keys[k] ? 'configured' : 'missing'));
                    });
                    html += escapeHtml(cfg.join(', '));
                }
                if ((!nps.provider_order || !nps.provider_order.length) && (!nps.configured_keys || Object.keys(nps.configured_keys).length === 0) && nps.message) {
                    html += escapeHtml(String(nps.message));
                }
                html += '</p>';
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

    function openScoreModal(runId, symbol) {
        var wrap = document.getElementById('rec-score-modal-wrap');
        var bodyEl = document.getElementById('rec-score-modal-body');
        var titleEl = document.getElementById('rec-score-modal-title');
        if (!wrap || !bodyEl || !titleEl || !runId || !symbol) return;
        titleEl.textContent = 'Score breakdown: ' + symbol;
        bodyEl.innerHTML = '<p class="muted">Loading…</p>';
        wrap.style.display = 'block';
        wrap.setAttribute('aria-hidden', 'false');
        wrap.querySelector('.rec-score-modal-backdrop').setAttribute('aria-hidden', 'false');

        fetchExplain(runId, symbol).then(function (data) {
            var items = data && data.items || [];
            var match = null;
            items.forEach(function (it) {
                if ((it.symbol || '').toUpperCase() === symbol.toUpperCase()) match = it;
            });
            var ex = match && match.explanation;
            var breakdown = ex && ex.score_breakdown;
            if (!breakdown) {
                bodyEl.innerHTML = '<p class="muted">No score breakdown available.</p>' +
                    (ex && ex.why_selected && ex.why_selected.length ? '<h4>Why selected</h4><ul>' + ex.why_selected.map(function (s) { return '<li>' + escapeHtml(String(s)) + '</li>'; }).join('') + '</ul>' : '');
                return;
            }
            var html = '<p class="rec-score-breakdown-desc">' + escapeHtml(breakdown.description || '') + '</p><table class="rec-score-breakdown-table"><tbody>';
            var keys = ['base', 'risk_band_match', 'industry_match', 'loss_aversion_bonus', 'sharpe_contribution', 'weight_penalty', 'volatility_penalty', 'heuristic_score', 'model_score', 'combined', 'total'];
            keys.forEach(function (k) {
                if (breakdown[k] != null && breakdown[k] !== undefined) {
                    var label = k.replace(/_/g, ' ');
                    html += '<tr><td>' + escapeHtml(label) + '</td><td>' + escapeHtml(String(breakdown[k])) + '</td></tr>';
                }
            });
            html += '</tbody></table>';
            bodyEl.innerHTML = html;
        }).catch(function () {
            bodyEl.innerHTML = '<p class="muted">Failed to load score breakdown.</p>';
        });
    }

    function closeScoreModal() {
        var wrap = document.getElementById('rec-score-modal-wrap');
        if (!wrap) return;
        wrap.style.display = 'none';
        wrap.setAttribute('aria-hidden', 'true');
        var backdrop = wrap.querySelector('.rec-score-modal-backdrop');
        if (backdrop) backdrop.setAttribute('aria-hidden', 'true');
    }

    function init() {
        var listEl = document.getElementById('rec-list');
        var statusEl = document.getElementById('rec-status');
        var summaryEl = document.getElementById('rec-portfolio-summary');
        if (!listEl || !statusEl) return;

        fetchRiskProfile().then(function (profile) {
            if (profile) {
                var riskEl = document.getElementById('rec-pref-risk');
                var indEl = document.getElementById('rec-pref-industries');
                var sharpeEl = document.getElementById('rec-pref-sharpe');
                var lossEl = document.getElementById('rec-pref-loss');
                var useFinanceEl = document.getElementById('rec-pref-use-finance');
                if (riskEl && profile.risk_tolerance) riskEl.value = profile.risk_tolerance;
                if (indEl && profile.industry_preferences && profile.industry_preferences.length)
                    indEl.value = profile.industry_preferences.join(', ');
                if (sharpeEl && profile.sharpe_objective != null) sharpeEl.value = Number(profile.sharpe_objective).toFixed(2);
                if (lossEl && profile.loss_aversion) lossEl.value = profile.loss_aversion;
                if (useFinanceEl) useFinanceEl.checked = !!profile.use_finance_data_for_recommendations;
            }
        });

        var savePrefsBtn = document.getElementById('rec-prefs-save');
        if (savePrefsBtn) {
            savePrefsBtn.addEventListener('click', function () {
                var riskEl = document.getElementById('rec-pref-risk');
                var indEl = document.getElementById('rec-pref-industries');
                var sharpeEl = document.getElementById('rec-pref-sharpe');
                var lossEl = document.getElementById('rec-pref-loss');
                var useFinanceEl = document.getElementById('rec-pref-use-finance');
                var industries = (indEl && indEl.value.trim()) ? indEl.value.trim().split(/\s*,\s*/).filter(Boolean) : null;
                var sharpe = sharpeEl && sharpeEl.value.trim() ? parseFloat(sharpeEl.value, 10) : null;
                if (sharpe !== null && isNaN(sharpe)) sharpe = null;
                var payload = {
                    risk_tolerance: riskEl ? riskEl.value : undefined,
                    industry_preferences: industries,
                    sharpe_objective: sharpe,
                    loss_aversion: lossEl ? lossEl.value : undefined,
                    use_finance_data_for_recommendations: useFinanceEl ? useFinanceEl.checked : undefined
                };
                savePrefsBtn.disabled = true;
                saveRiskProfile(payload).then(function () {
                    savePrefsBtn.textContent = 'Saved';
                    setTimeout(function () { savePrefsBtn.textContent = 'Save preferences'; savePrefsBtn.disabled = false; }, 1500);
                }).catch(function (err) {
                    alert(err.message || 'Failed to save preferences');
                    savePrefsBtn.disabled = false;
                });
            });
        }

        fetchLatest(1, true).then(function (data) {
            renderList(listEl, statusEl, data, 1);
            var hasRun = data && data.run;
            var hasItems = data && data.items && data.items.length > 0;
            if (summaryEl) {
                if (hasRun && (hasItems || (data && data.portfolio))) renderSummary(summaryEl, data);
                else renderSummary(summaryEl, null);
            }
        }).catch(function () {
            statusEl.textContent = 'Could not load latest recommendations. Make sure you are logged in.';
            if (summaryEl) summaryEl.innerHTML = '<p class="muted">Log in and try again to see portfolio risk metrics here.</p>';
        });

        var runBtn = document.getElementById('rec-run-btn');
        if (runBtn) {
            runBtn.addEventListener('click', function () {
                statusEl.textContent = 'Generating recommendations…';
                runBtn.disabled = true;
                runRecommendations().then(function (data) {
                    renderSummary(summaryEl, data);
                    return fetchLatest(1, true);
                }).then(function (data) {
                    renderList(listEl, statusEl, data, 1);
                }).catch(function (err) {
                    alert(err.message || 'Failed to run recommendations');
                }).finally(function () {
                    runBtn.disabled = false;
                });
            });
        }

        listEl.addEventListener('click', function (e) {
            var explainBtn = e.target.closest('.rec-explain-btn');
            if (explainBtn) {
                var symbol = explainBtn.getAttribute('data-symbol') || '';
                var runId = listEl.getAttribute('data-run-id') || '';
                openExplainDrawer(listEl, runId, symbol);
                return;
            }
            var scoreBtn = e.target.closest('.rec-score-btn');
            if (scoreBtn) {
                var sym = scoreBtn.getAttribute('data-symbol') || '';
                var runId = listEl.getAttribute('data-run-id') || '';
                openScoreModal(runId, sym);
                return;
            }
            var prevBtn = e.target.closest('.rec-pagination-prev');
            if (prevBtn) {
                var page = parseInt(prevBtn.getAttribute('data-page'), 10) || 1;
                statusEl.textContent = 'Loading page ' + page + '…';
                fetchLatest(page, true).then(function (data) {
                    renderList(listEl, statusEl, data, page);
                }).catch(function () {
                    statusEl.textContent = 'Failed to load page.';
                });
                return;
            }
            var nextBtn = e.target.closest('.rec-pagination-next');
            if (nextBtn) {
                var page = parseInt(nextBtn.getAttribute('data-page'), 10) || 1;
                statusEl.textContent = 'Loading page ' + page + '…';
                fetchLatest(page, true).then(function (data) {
                    renderList(listEl, statusEl, data, page);
                }).catch(function () {
                    statusEl.textContent = 'Failed to load page.';
                });
            }
        });

        var closeBtn = document.getElementById('rec-explain-close');
        if (closeBtn) closeBtn.addEventListener('click', closeExplainDrawer);
        var backdrop = document.getElementById('rec-explain-backdrop');
        if (backdrop) backdrop.addEventListener('click', closeExplainDrawer);

        var scoreCloseBtn = document.getElementById('rec-score-modal-close');
        if (scoreCloseBtn) scoreCloseBtn.addEventListener('click', closeScoreModal);
        var scoreBackdrop = document.querySelector('.rec-score-modal-backdrop');
        if (scoreBackdrop) scoreBackdrop.addEventListener('click', closeScoreModal);
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') {
                if (document.getElementById('rec-score-modal-wrap') && document.getElementById('rec-score-modal-wrap').style.display === 'block') {
                    closeScoreModal();
                }
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

