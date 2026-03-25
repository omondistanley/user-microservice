"use strict";
(function() {
  "use strict";
  var API = window.API_BASE || "";
  var recState = {
    runId: "",
    currentPage: 1,
    latestPayload: null,
    pageState: ""
  };
  function _isVolatileBuyAdjacentCopy(s) {
    if (!s) return false;
    return /tax-?loss|harvest|tlh|buy\s+more|add\s+to\s+holdings|increase\s+exposure/i.test(String(s));
  }
  function apiErrorDetail(body) {
    if (!body) return "Request failed";
    var d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      return d.map(function(e) {
        var loc = e.loc && e.loc.slice(1).join(".") || "";
        return (loc ? loc + ": " : "") + (e.msg || e.message || "");
      }).join("; ");
    }
    return body.detail ? String(body.detail) : "Request failed";
  }
  function getAuthHeaders() {
    if (window.Auth && window.Auth.getAuthHeaders) {
      return window.Auth.getAuthHeaders();
    }
    var token = window.Auth && window.Auth.getToken && window.Auth.getToken();
    if (!token) return {};
    return { "Authorization": "Bearer " + token, "Content-Type": "application/json" };
  }
  function runRecommendations() {
    var headers = getAuthHeaders();
    headers["Content-Type"] = "application/json";
    return fetch(API + "/api/v1/recommendations/run", {
      method: "POST",
      headers,
      body: "{}"
    }).then(function(r) {
      if (!r.ok) {
        return r.json().catch(function() {
          return {};
        }).then(function(body) {
          throw new Error(apiErrorDetail(body) || "Failed to run recommendations");
        });
      }
      return r.json();
    });
  }
  var PAGE_SIZE = 20;
  function fetchLatest(page, enrich) {
    page = page || 1;
    var url = API + "/api/v1/recommendations/latest?page=" + page + "&page_size=" + PAGE_SIZE;
    if (enrich) url += "&enrich=1";
    return fetch(url, { headers: getAuthHeaders() }).then(function(r) {
      if (!r.ok) throw new Error("Failed to load latest recommendations");
      return r.json();
    });
  }
  function fetchExplain(runId, symbol) {
    var url = API + "/api/v1/recommendations/" + encodeURIComponent(runId) + "/explain";
    if (symbol) url += "?symbol=" + encodeURIComponent(symbol);
    return fetch(url, { headers: getAuthHeaders() }).then(function(r) {
      if (!r.ok) throw new Error("Failed to load explanation");
      return r.json();
    });
  }
  function fetchExplainSymbol(runId, symbol) {
    var url = API + "/api/v1/recommendations/" + encodeURIComponent(runId) + "/explain/" + encodeURIComponent(symbol);
    return fetch(url, { headers: getAuthHeaders() }).then(function(r) {
      if (!r.ok) throw new Error("Failed to load explanation");
      return r.json();
    });
  }
  function fetchRiskProfile() {
    return fetch(API + "/api/v1/risk-profile", { headers: getAuthHeaders() }).then(function(r) {
      if (!r.ok) return null;
      return r.json();
    }).catch(function() {
      return null;
    });
  }
  function saveRiskProfile(payload) {
    var headers = getAuthHeaders();
    headers["Content-Type"] = "application/json";
    var body = {};
    if (payload.risk_tolerance != null) body.risk_tolerance = payload.risk_tolerance;
    if (payload.industry_preferences != null) body.industry_preferences = payload.industry_preferences;
    if (payload.sharpe_objective != null) body.sharpe_objective = payload.sharpe_objective;
    if (payload.loss_aversion != null) body.loss_aversion = payload.loss_aversion;
    if (payload.use_finance_data_for_recommendations != null) body.use_finance_data_for_recommendations = !!payload.use_finance_data_for_recommendations;
    return fetch(API + "/api/v1/risk-profile", {
      method: "PUT",
      headers,
      body: JSON.stringify(body)
    }).then(function(r) {
      if (!r.ok) return r.json().catch(function() {
        return {};
      }).then(function(b) {
        throw new Error(apiErrorDetail(b) || "Failed to save preferences");
      });
      return r.json();
    });
  }
  function formatPct(x) {
    var n = Number(x);
    if (!isFinite(n)) return "\u2014";
    return (n * 100).toFixed(2) + "%";
  }
  function formatNum2(x) {
    var n = Number(x);
    if (!isFinite(n)) return "\u2014";
    return n.toFixed(2);
  }
  function escapeHtml(s) {
    if (s == null) return "";
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }
  function _riskLabelFromVol(vol) {
    if (!isFinite(vol)) return "Moderate";
    if (vol < 0.12) return "Low";
    if (vol < 0.18) return "Moderate";
    if (vol < 0.28) return "Elevated";
    return "High";
  }
  function renderSummary(summaryEl, data) {
    if (!summaryEl) return;
    if (!data || !data.portfolio) {
      summaryEl.innerHTML = '<p class="muted">Run recommendations above to see portfolio risk metrics (Sharpe, volatility, drawdown). Add holdings on the <a href="/investments">Investments</a> page first for meaningful numbers.</p>';
      return;
    }
    var p = data.portfolio;
    var ui = data.ui_insights;
    if (!ui && p) {
      var hhi = parseFloat(p.hhi);
      var divScore = Math.max(0, Math.min(100, Math.round(100 * (1 - (isFinite(hhi) ? hhi : 1)))));
      var vol = parseFloat(p.volatility_annual);
      ui = {
        diversification_score_0_100: divScore,
        risk_label: _riskLabelFromVol(vol),
        diversification_status: divScore >= 70 ? "OPTIMAL" : divScore >= 40 ? "ADEQUATE" : "CONCENTRATED",
        engine_label: "AI Insights Engine",
        last_run_at: data.run && data.run.created_at ? data.run.created_at : ""
      };
    }
    var html = "";
    if (ui) {
      html += '<div class="rec-ui-insights" style="margin-bottom:1rem;padding:1rem 1.25rem;border-radius:0.75rem;background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);color:#e2e8f0;">';
      html += '<p style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.15em;opacity:0.7;margin:0;">' + escapeHtml(ui.engine_label || "Insights") + "</p>";
      html += '<p style="font-size:1.35rem;font-weight:800;margin:0.35rem 0;">Diversification ' + escapeHtml(String(ui.diversification_score_0_100 != null ? ui.diversification_score_0_100 : "\u2014")) + '<span style="opacity:0.5;font-size:0.95rem;">/100</span></p>';
      html += '<p style="margin:0;font-size:0.9rem;"><span style="opacity:0.75;">Risk</span> ' + escapeHtml(ui.risk_label || "\u2014") + ' \xB7 <span style="opacity:0.75;">Status</span> ' + escapeHtml(ui.diversification_status || "\u2014") + "</p>";
      if (ui.last_run_at) html += '<p style="margin:0.5rem 0 0;font-size:0.78rem;opacity:0.65;">Last run ' + escapeHtml(String(ui.last_run_at)) + "</p>";
      html += "</div>";
    }
    html += '<ul class="portfolio-metrics">';
    html += "<li><strong>Total value</strong>: $" + escapeHtml(formatNum2(p.total_value)) + "</li>";
    html += "<li><strong>Total cost basis</strong>: $" + escapeHtml(formatNum2(p.total_cost_basis)) + "</li>";
    html += "<li><strong>Unrealized P/L</strong>: $" + escapeHtml(formatNum2(p.unrealized_pl)) + "</li>";
    html += "<li><strong>Realized P/L</strong>: $" + escapeHtml(formatNum2(p.realized_pl)) + "</li>";
    html += "<li><strong>Sharpe ratio</strong>: " + escapeHtml(formatNum2(p.sharpe)) + "</li>";
    html += "<li><strong>Volatility (annual)</strong>: " + escapeHtml(formatNum2(p.volatility_annual)) + "</li>";
    html += "<li><strong>Max drawdown</strong>: " + escapeHtml(formatNum2(p.max_drawdown)) + "</li>";
    html += "<li><strong>Top position weight</strong>: " + escapeHtml(formatNum2(p.top1_weight)) + "</li>";
    if (p.top3_weight != null && p.top3_weight !== "") {
      html += "<li><strong>Top 3 weight</strong>: " + escapeHtml(formatNum2(p.top3_weight)) + "</li>";
    }
    if (p.hhi != null && p.hhi !== "") {
      html += "<li><strong>Concentration (HHI)</strong>: " + escapeHtml(formatNum2(p.hhi)) + "</li>";
    }
    if (p.position_count != null && p.position_count !== "") {
      html += "<li><strong>Positions</strong>: " + escapeHtml(String(p.position_count)) + "</li>";
    }
    if (p.snapshot_date) {
      html += "<li><strong>Snapshot as of</strong>: " + escapeHtml(String(p.snapshot_date)) + "</li>";
    }
    html += "</ul>";
    if (p.holdings_top && p.holdings_top.length) {
      html += '<h4 style="margin:1rem 0 0.5rem;font-size:0.95rem;">Largest positions</h4><ul class="portfolio-holdings-top" style="font-size:0.875rem;padding-left:1.1rem;">';
      p.holdings_top.slice(0, 8).forEach(function(h) {
        html += "<li><strong>" + escapeHtml(h.symbol || "\u2014") + "</strong> \u2014 weight " + escapeHtml(formatNum2(h.weight)) + (h.source ? " \xB7 " + escapeHtml(h.source) : "") + "</li>";
      });
      html += "</ul>";
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
    currentPage = currentPage != null ? currentPage : pagination.page || 1;
    if (!run) {
      statusEl.textContent = "Click \u201CGenerate recommendations\u201D to get a starter list (no holdings needed) or to rank your current holdings. Save your preferences above first for best results.";
      listEl.innerHTML = '<p class="muted">Generate recommendations to see analyst suggestions. With no holdings you get a starter portfolio; with holdings you get ranked positions and risk notes.</p><div id="rec-pagination" class="rec-pagination"></div>';
      if (listEl.setAttribute) listEl.setAttribute("data-run-id", "");
      return;
    }
    statusEl.textContent = "Latest run at " + (run.created_at || "\u2014");
    var html = '<div class="rec-cards-grid">';
    if (!items.length) {
      html += '<p class="muted">No items on this page.</p>';
    } else {
      items.forEach(function(it, idx) {
        var sym = (it.symbol || "").toUpperCase();
        var name = it.full_name || it.description || "\u2014";
        var sector = it.sector || "\u2014";
        var lastPrice = it.last_price != null ? "$" + escapeHtml(formatNum2(it.last_price)) : "\u2014";
        var changePct = it.change_pct != null ? (Number(it.change_pct) >= 0 ? "+" : "") + Number(it.change_pct).toFixed(2) + "%" : "\u2014";
        var trend1m = it.trend_1m_pct != null ? (Number(it.trend_1m_pct) >= 0 ? "+" : "") + Number(it.trend_1m_pct).toFixed(2) + "%" : "\u2014";
        var scoreStr = formatNum2(it.score);
        var hideAdd = payload && payload.page_state === "volatile";
        var eg = it.earnings_gate && typeof it.earnings_gate === "object" ? it.earnings_gate : {};
        var badges = Array.isArray(it.data_badges) ? it.data_badges : [];
        html += '<article class="rec-card recommendation-item" data-index="' + idx + '">';
        html += '<header class="rec-card-head"><div>';
        html += '<div class="rec-card-symbol">' + escapeHtml(sym) + "</div>";
        html += '<div class="rec-card-name muted">' + escapeHtml(name) + "</div></div>";
        html += '<div class="rec-card-scores">';
        html += '<button type="button" class="rec-score-pill rec-score-btn" data-symbol="' + escapeHtml(sym) + '" title="Score breakdown">' + escapeHtml(scoreStr) + "</button>";
        html += '<span class="rec-conf-pill">' + escapeHtml(formatPct(it.confidence)) + " conf.</span></div></header>";
        html += '<p class="rec-card-sector muted" style="font-size:0.8125rem;margin:0 0 0.5rem;">Sector: ' + escapeHtml(sector) + "</p>";
        if (it.why_shown_one_line) {
          html += '<p class="rec-card-why"><span class="rec-card-why-label">Why shown</span> ' + escapeHtml(it.why_shown_one_line) + "</p>";
        }
        if (it.bull_case || it.bear_case) {
          html += '<div class="rec-card-thesis">';
          if (it.bull_case) html += '<div class="rec-thesis-bull"><strong>Bull case</strong> ' + escapeHtml(it.bull_case) + "</div>";
          if (it.bear_case) html += '<div class="rec-thesis-bear"><strong>Bear case</strong> ' + escapeHtml(it.bear_case) + "</div>";
          html += "</div>";
        }
        if (badges.length) {
          html += '<div class="rec-card-badges">';
          badges.forEach(function(b) {
            html += '<span class="rec-data-badge">' + escapeHtml(String(b)) + "</span>";
          });
          html += "</div>";
        }
        if (eg.note || eg.status) {
          html += '<p class="rec-earnings-gate muted" style="font-size:0.78rem;margin:0.35rem 0;"><strong>Earnings</strong> ';
          html += escapeHtml(String(eg.status || "\u2014")) + (eg.note ? " \u2014 " + escapeHtml(String(eg.note)) : "") + "</p>";
        }
        if (it.consensus && it.consensus.detail) {
          var cl = it.consensus.label || "Consensus";
          html += '<p class="muted" style="font-size:0.78rem;margin:0.25rem 0;"><strong>' + escapeHtml(String(cl)) + "</strong> " + escapeHtml(String(it.consensus.detail)) + "</p>";
        }
        html += '<div class="rec-card-market muted" style="font-size:0.8125rem;display:flex;flex-wrap:wrap;gap:0.75rem;margin:0.5rem 0;">';
        html += "<span>Last " + lastPrice + "</span><span>Day " + escapeHtml(changePct) + "</span><span>1M " + escapeHtml(trend1m) + "</span>";
        html += "</div>";
        html += '<footer class="rec-card-actions">';
        html += '<button type="button" class="btn btn-secondary btn-sm rec-explain-btn" data-symbol="' + escapeHtml(sym) + '">View details</button>';
        if (!hideAdd) {
          html += '<a href="/investments?add=' + encodeURIComponent(sym) + '" class="btn btn-sm btn-ghost rec-add-holding" data-symbol="' + escapeHtml(sym) + '">Add to holdings</a>';
        }
        html += "</footer>";
        html += '<p class="rec-card-disclaimer" style="font-size:0.7rem;opacity:0.75;margin:0.5rem 0 0;">Informational only. Not financial advice. Not a recommendation to buy, sell, or hold any security.</p>';
        html += "</article>";
      });
    }
    html += "</div>";
    html += '<div id="rec-pagination" class="rec-pagination">';
    if (totalItems > 0) {
      html += '<span class="rec-pagination-info">Page ' + currentPage + " of " + totalPages + " (" + totalItems + " total)</span>";
      if (currentPage > 1) {
        html += ' <button type="button" class="btn btn-sm rec-pagination-prev" data-page="' + (currentPage - 1) + '">Prev</button>';
      }
      if (currentPage < totalPages) {
        html += ' <button type="button" class="btn btn-sm rec-pagination-next" data-page="' + (currentPage + 1) + '">Next</button>';
      }
    }
    html += "</div>";
    listEl.innerHTML = html;
    listEl.setAttribute("data-run-id", run.run_id || "");
    listEl.setAttribute("data-current-page", String(currentPage));
    recState.runId = run.run_id || "";
    recState.currentPage = currentPage;
    recState.latestPayload = payload || null;
    renderActionQueue(payload);
  }
  function renderActionQueue(payload) {
    var card = document.getElementById("rec-action-queue-card");
    var list = document.getElementById("rec-action-queue-list");
    if (!card || !list) return;
    var aq = payload && payload.action_queue;
    if (!aq || !aq.length) {
      card.style.display = "none";
      list.innerHTML = "";
      return;
    }
    var html = '<ul class="rec-action-queue-ul">';
    aq.forEach(function(a) {
      html += '<li class="rec-action-queue-li">';
      html += "<strong>" + escapeHtml(a.symbol || "") + '</strong> <span class="muted">' + escapeHtml(a.headline || "") + "</span>";
      html += '<p class="muted" style="font-size:0.8125rem;margin:0.25rem 0 0;line-height:1.4;">' + escapeHtml(a.detail || "") + "</p>";
      html += "</li>";
    });
    html += "</ul>";
    list.innerHTML = html;
    card.style.display = "block";
  }
  function openExplainDrawer(rootEl, runId, symbol) {
    var wrap = document.getElementById("rec-explain-wrap");
    if (!wrap || !runId) return;
    var bodyEl = document.getElementById("rec-explain-body");
    var titleEl = document.getElementById("rec-explain-title");
    if (titleEl) titleEl.textContent = "Why " + symbol + "?";
    bodyEl.innerHTML = '<p class="muted">Loading details\u2026</p>';
    wrap.style.display = "block";
    wrap.setAttribute("aria-hidden", "false");
    fetchExplainSymbol(runId, symbol).then(function(data) {
      var match = data || null;
      if (!match || !match.explanation) {
        bodyEl.innerHTML = '<p class="muted">No explanation available.</p>';
        return;
      }
      var ex = match.explanation;
      if (!ex || typeof ex !== "object") ex = {};
      var volatileMode = recState.pageState === "volatile";
      if (!ex.data_freshness) ex.data_freshness = { provider: "Unavailable", stale_seconds: null };
      if (!ex.market) ex.market = {};
      if (!ex.enrichment) ex.enrichment = {};
      if (!ex.sentiment_trend_7d) ex.sentiment_trend_7d = { daily_scores: [], rolling_avg_7d: null };
      if (!ex.news_factors) ex.news_factors = { recent_news: [] };
      if (!ex.news_provider_status) ex.news_provider_status = { provider_order: [], configured_keys: {}, message: "No diagnostics returned by backend" };
      var html = "";
      if (ex.personalized_with_finance_data) {
        html += '<p class="muted" style="font-size:0.85rem; margin-bottom:1rem;">Personalized using your savings, goals, and budget data.</p>';
      }
      if (ex.security) {
        var sec = ex.security;
        html += "<h4>Security</h4><ul>";
        html += "<li><strong>Name</strong>: " + escapeHtml(sec.full_name || "\u2014") + "</li>";
        html += "<li><strong>Sector</strong>: " + escapeHtml(sec.sector || "\u2014") + "</li>";
        html += "<li><strong>Asset type</strong>: " + escapeHtml(sec.asset_type || "\u2014") + "</li>";
        if (sec.why_it_matters) {
          html += "<li><strong>Why it matters</strong>: " + escapeHtml(String(sec.why_it_matters)) + "</li>";
        }
        html += "</ul>";
      }
      if (ex.market) {
        var m = ex.market;
        html += "<h4>Market</h4><ul>";
        html += "<li><strong>Current price</strong>: $" + escapeHtml(m.current_price != null ? formatNum2(m.current_price) : "\u2014") + "</li>";
        if (m.as_of) html += "<li><strong>As of</strong>: " + escapeHtml(String(m.as_of)) + "</li>";
        if (m.trend_1m_pct != null) html += "<li><strong>1M trend</strong>: " + escapeHtml(Number(m.trend_1m_pct).toFixed(2)) + "%</li>";
        if (m["52w_high"] != null) html += "<li><strong>52w high</strong>: $" + escapeHtml(formatNum2(m["52w_high"])) + "</li>";
        if (m["52w_low"] != null) html += "<li><strong>52w low</strong>: $" + escapeHtml(formatNum2(m["52w_low"])) + "</li>";
        html += "</ul>";
      }
      if (ex.enrichment) {
        var en = ex.enrichment;
        html += "<h4>Enrichment</h4><ul>";
        if (en.quote) {
          html += "<li><strong>Live price</strong>: $" + escapeHtml(en.quote.price != null ? formatNum2(en.quote.price) : "\u2014") + "</li>";
          if (en.quote.as_of) html += "<li><strong>As of</strong>: " + escapeHtml(String(en.quote.as_of)) + "</li>";
          if (en.quote.change_pct != null) html += "<li><strong>Day change</strong>: " + escapeHtml(Number(en.quote.change_pct).toFixed(2)) + "%</li>";
        }
        if (en.trend_1m_pct != null) html += "<li><strong>1M trend</strong>: " + escapeHtml(Number(en.trend_1m_pct).toFixed(2)) + "%</li>";
        if (en["52w_high"] != null) html += "<li><strong>52w high</strong>: $" + escapeHtml(formatNum2(en["52w_high"])) + "</li>";
        if (en["52w_low"] != null) html += "<li><strong>52w low</strong>: $" + escapeHtml(formatNum2(en["52w_low"])) + "</li>";
        if (en.data_freshness && en.data_freshness.provider) html += "<li><strong>Provider</strong>: " + escapeHtml(String(en.data_freshness.provider)) + "</li>";
        html += "</ul>";
        if (en.recent_news && en.recent_news.length) {
          html += '<p class="rec-enrichment-news"><strong>Recent news</strong> <span class="muted">(provider tags where available)</span></p><ul class="rec-news-list">';
          en.recent_news.forEach(function(n) {
            var title = (n.title || "Headline").substring(0, 80);
            if ((n.title || "").length > 80) title += "\u2026";
            var link = n.url ? '<a href="' + escapeHtml(n.url) + '" target="_blank" rel="noopener">' + escapeHtml(title) + "</a>" : escapeHtml(title);
            var prov = n.source_provider ? ' <span class="muted">[' + escapeHtml(String(n.source_provider)) + "]</span>" : "";
            html += "<li>" + link + prov + (n.published_at ? ' <span class="muted">' + escapeHtml(String(n.published_at)) + "</span>" : "") + "</li>";
          });
          html += "</ul>";
        }
      }
      html += "<h4>Market sentiment</h4>";
      if (ex.sentiment_summary) {
        html += "<p>" + escapeHtml(String(ex.sentiment_summary)) + "</p>";
        if (ex.sentiment_context) {
          html += '<p class="muted" style="font-size:0.8rem;">Source: ' + escapeHtml(String(ex.sentiment_context)) + "</p>";
        }
        if (ex.sentiment_trend_7d && ex.sentiment_trend_7d.daily_scores && ex.sentiment_trend_7d.daily_scores.length) {
          html += '<p class="muted" style="font-size:0.85rem;">7-day rolling average (stored scores): ' + (ex.sentiment_trend_7d.rolling_avg_7d != null ? escapeHtml(Number(ex.sentiment_trend_7d.rolling_avg_7d).toFixed(2)) : "\u2014") + "</p>";
        }
      } else if (ex.sentiment_trend_7d && ex.sentiment_trend_7d.daily_scores && ex.sentiment_trend_7d.daily_scores.length) {
        html += '<p class="muted">Summarizing from trend\u2026</p>';
      } else {
        html += '<p class="muted">No 7-day sentiment series returned; see News &amp; events for headline context (Benzinga / Finnhub / other configured feeds).</p>';
      }
      if (ex.why_selected_evidence && ex.why_selected_evidence.length) {
        html += '<h4>Why this appeared in your list (data &amp; settings)</h4><ul class="rec-evidence-list">';
        ex.why_selected_evidence.forEach(function(row) {
          var det = row.detail || "";
          if (volatileMode && _isVolatileBuyAdjacentCopy(det)) return;
          var src = row.source || "Input";
          html += "<li><strong>" + escapeHtml(String(src)) + "</strong>: " + escapeHtml(String(det)) + "</li>";
        });
        html += "</ul>";
      } else if (ex.why_selected && ex.why_selected.length) {
        html += "<h4>Why this appeared in your list</h4><ul>";
        ex.why_selected.forEach(function(s) {
          if (volatileMode && _isVolatileBuyAdjacentCopy(s)) return;
          html += "<li>" + escapeHtml(String(s)) + "</li>";
        });
        html += "</ul>";
      }
      if (ex.risk_return_narrative && ex.risk_return_narrative.length) {
        html += "<h4>Risk &amp; return (how we use these metrics)</h4><ul>";
        ex.risk_return_narrative.forEach(function(line) {
          html += "<li>" + escapeHtml(String(line)) + "</li>";
        });
        html += "</ul>";
      }
      if (ex.risk_metrics) {
        var rm = ex.risk_metrics;
        var sharpeStr = rm.sharpe != null && String(rm.sharpe).indexOf("N/A") === -1 ? formatNum2(rm.sharpe) : rm.sharpe != null ? String(rm.sharpe) : "\u2014";
        var volStr = rm.volatility_annual != null && String(rm.volatility_annual).indexOf("N/A") === -1 ? formatNum2(rm.volatility_annual) : rm.volatility_annual != null ? String(rm.volatility_annual) : "\u2014";
        var mddStr = rm.max_drawdown != null && String(rm.max_drawdown).indexOf("N/A") === -1 ? formatNum2(rm.max_drawdown) : rm.max_drawdown != null ? String(rm.max_drawdown) : "\u2014";
        html += "<h4>Risk &amp; return (numbers)</h4><ul>";
        html += "<li><strong>Sharpe</strong>: " + escapeHtml(sharpeStr) + "</li>";
        html += "<li><strong>Volatility (annual)</strong>: " + escapeHtml(volStr) + "</li>";
        html += "<li><strong>Max drawdown</strong>: " + escapeHtml(mddStr) + "</li>";
        html += "</ul>";
      }
      if (ex.data_freshness) {
        html += "<h4>Data freshness</h4><ul>";
        if (ex.data_freshness.provider) {
          html += "<li><strong>Provider</strong>: " + escapeHtml(String(ex.data_freshness.provider)) + "</li>";
        }
        if (ex.data_freshness.stale_seconds != null) {
          html += "<li><strong>Stale (seconds)</strong>: " + escapeHtml(String(ex.data_freshness.stale_seconds)) + "</li>";
        }
        html += "</ul>";
      }
      if (ex.confidence) {
        html += "<h4>Confidence</h4><p>Confidence index: " + formatPct(ex.confidence.value) + "</p>";
      }
      if (ex.analyst_note_detail || ex.analyst_note) {
        html += '<h4>Analyst-style note</h4><p style="white-space:pre-wrap;">' + escapeHtml(String(ex.analyst_note_detail || ex.analyst_note)) + "</p>";
      }
      if (ex.narrative) {
        html += "<h4>Summary</h4><p>" + escapeHtml(String(ex.narrative)) + "</p>";
      }
      if (ex.news_factors) {
        html += "<h4>News &amp; events</h4>";
        if (ex.news_factors.recent_news && ex.news_factors.recent_news.length) {
          html += '<ul class="rec-news-list">';
          ex.news_factors.recent_news.forEach(function(n) {
            var title = (n.title || "Headline").substring(0, 80);
            if ((n.title || "").length > 80) title += "\u2026";
            var link = n.url ? '<a href="' + escapeHtml(n.url) + '" target="_blank" rel="noopener">' + escapeHtml(title) + "</a>" : escapeHtml(title);
            var prov = n.source_provider ? ' <span class="muted">[' + escapeHtml(String(n.source_provider)) + "]</span>" : "";
            html += "<li>" + link + prov + (n.published_at ? ' <span class="muted">' + escapeHtml(String(n.published_at)) + "</span>" : "") + "</li>";
          });
          html += "</ul>";
        } else if (ex.news_factors.event_flags && ex.news_factors.event_flags.length) {
          html += "<p>Events: " + escapeHtml(ex.news_factors.event_flags.join(", ")) + "</p>";
        } else {
          html += '<p class="muted">No headlines returned for this symbol in the current window. Check Benzinga / Finnhub / Alpha Vantage / Twelve Data keys in environment.</p>';
        }
      }
      if (ex.news_provider_status) {
        var nps = ex.news_provider_status;
        html += '<p class="muted" style="font-size:0.8rem;">';
        html += "Provider diagnostics: ";
        if (nps.provider_order && nps.provider_order.length) {
          html += "order=" + escapeHtml(String(nps.provider_order.join(","))) + "; ";
        }
        if (nps.configured_keys) {
          var cfg = [];
          Object.keys(nps.configured_keys).forEach(function(k) {
            cfg.push(k + "=" + (nps.configured_keys[k] ? "configured" : "missing"));
          });
          html += escapeHtml(cfg.join(", "));
        }
        if ((!nps.provider_order || !nps.provider_order.length) && (!nps.configured_keys || Object.keys(nps.configured_keys).length === 0) && nps.message) {
          html += escapeHtml(String(nps.message));
        }
        html += "</p>";
      }
      bodyEl.innerHTML = html;
    }).catch(function() {
      bodyEl.innerHTML = '<p class="muted">Failed to load explanation.</p>';
    });
  }
  function closeExplainDrawer() {
    var wrap = document.getElementById("rec-explain-wrap");
    if (!wrap) return;
    wrap.style.display = "none";
    wrap.setAttribute("aria-hidden", "true");
  }
  function openScoreModal(runId, symbol) {
    var wrap = document.getElementById("rec-score-modal-wrap");
    var bodyEl = document.getElementById("rec-score-modal-body");
    var titleEl = document.getElementById("rec-score-modal-title");
    if (!wrap || !bodyEl || !titleEl || !runId || !symbol) return;
    titleEl.textContent = "Score breakdown: " + symbol;
    bodyEl.innerHTML = '<p class="muted">Loading\u2026</p>';
    wrap.style.display = "block";
    wrap.setAttribute("aria-hidden", "false");
    wrap.querySelector(".rec-score-modal-backdrop").setAttribute("aria-hidden", "false");
    fetchExplainSymbol(runId, symbol).then(function(data) {
      var match = data || null;
      var ex = match && match.explanation;
      var breakdown = ex && ex.score_breakdown;
      var disclaimer = '<div class="rec-score-modal-disclaimer"><strong>Disclaimer.</strong> This breakdown shows how inputs were combined for this informational ranking. It is not personalized investment advice and does not account for everything relevant to your situation (taxes, employer plans, liquidity, or time horizon).</div>';
      if (!breakdown) {
        bodyEl.innerHTML = disclaimer + '<p class="muted">No score breakdown available.</p>' + (ex && ex.why_selected && ex.why_selected.length ? "<h4>Why selected</h4><ul>" + ex.why_selected.map(function(s) {
          return "<li>" + escapeHtml(String(s)) + "</li>";
        }).join("") + "</ul>" : "") + '<p class="rec-score-modal-meta"><a href="/settings/integrations">Link accounts</a> under Settings so cashflow and goals can refine context when you enable that option.</p>';
        return;
      }
      var html = disclaimer;
      html += '<p class="rec-score-modal-meta"><strong>Assumptions.</strong> Uses your risk profile, holdings weights, volatility/concentration heuristics, and optional linked finance data when enabled. Missing data appears as N/A or neutral defaults.</p>';
      html += '<p class="rec-score-breakdown-desc">' + escapeHtml(breakdown.description || "") + '</p><table class="rec-score-breakdown-table"><tbody>';
      var keys = ["base", "risk_band_match", "industry_match", "loss_aversion_bonus", "sharpe_contribution", "weight_penalty", "volatility_penalty", "heuristic_score", "model_score", "tlh_bonus", "tlh_harvestable_loss", "combined", "total"];
      var volatileRec = recState.pageState === "volatile";
      keys.forEach(function(k) {
        if (breakdown[k] == null || breakdown[k] === void 0) return;
        if (volatileRec && (k === "tlh_bonus" || k === "tlh_harvestable_loss")) return;
        var label = k.replace(/_/g, " ");
        html += "<tr><td>" + escapeHtml(label) + "</td><td>" + escapeHtml(String(breakdown[k])) + "</td></tr>";
      });
      html += "</tbody></table>";
      if (ex && ex.data_freshness) {
        html += '<div class="rec-score-modal-provenance"><strong>Market data</strong> provider: ' + escapeHtml(String(ex.data_freshness.provider || "\u2014"));
        if (ex.data_freshness.stale_seconds != null) html += " \xB7 stale ~" + escapeHtml(String(ex.data_freshness.stale_seconds)) + "s";
        html += "</div>";
      }
      if (ex && ex.news_provider_status && ex.news_provider_status.configured_keys) {
        var ck = ex.news_provider_status.configured_keys;
        var bits = [];
        Object.keys(ck).forEach(function(k) {
          bits.push(k + "=" + (ck[k] ? "on" : "off"));
        });
        html += '<div class="rec-score-modal-provenance"><strong>News providers</strong> ' + escapeHtml(bits.join(", ")) + "</div>";
      }
      html += '<p class="rec-score-modal-meta">What we may not know: tax lots in all brokers, restricted stock, private investments, and future cash needs. <a href="/settings/integrations">Review integrations</a> to improve data coverage.</p>';
      bodyEl.innerHTML = html;
    }).catch(function() {
      bodyEl.innerHTML = '<p class="muted">Failed to load score breakdown.</p>';
    });
  }
  function closeScoreModal() {
    var wrap = document.getElementById("rec-score-modal-wrap");
    if (!wrap) return;
    wrap.style.display = "none";
    wrap.setAttribute("aria-hidden", "true");
    var backdrop = wrap.querySelector(".rec-score-modal-backdrop");
    if (backdrop) backdrop.setAttribute("aria-hidden", "true");
  }
  function init() {
    var listEl = document.getElementById("rec-list");
    var statusEl = document.getElementById("rec-status");
    var summaryEl = document.getElementById("rec-portfolio-summary");
    if (!listEl || !statusEl) return;
    fetchRiskProfile().then(function(profile) {
      if (profile) {
        var riskEl = document.getElementById("rec-pref-risk");
        var indEl = document.getElementById("rec-pref-industries");
        var sharpeEl = document.getElementById("rec-pref-sharpe");
        var lossEl = document.getElementById("rec-pref-loss");
        var useFinanceEl = document.getElementById("rec-pref-use-finance");
        if (riskEl && profile.risk_tolerance) riskEl.value = profile.risk_tolerance;
        if (indEl && profile.industry_preferences && profile.industry_preferences.length)
          indEl.value = profile.industry_preferences.join(", ");
        if (sharpeEl && profile.sharpe_objective != null) sharpeEl.value = Number(profile.sharpe_objective).toFixed(2);
        if (lossEl && profile.loss_aversion) lossEl.value = profile.loss_aversion;
        if (useFinanceEl) useFinanceEl.checked = !!profile.use_finance_data_for_recommendations;
      }
    });
    var savePrefsBtn = document.getElementById("rec-prefs-save");
    if (savePrefsBtn) {
      savePrefsBtn.addEventListener("click", function() {
        var riskEl = document.getElementById("rec-pref-risk");
        var indEl = document.getElementById("rec-pref-industries");
        var sharpeEl = document.getElementById("rec-pref-sharpe");
        var lossEl = document.getElementById("rec-pref-loss");
        var useFinanceEl = document.getElementById("rec-pref-use-finance");
        var industries = indEl && indEl.value.trim() ? indEl.value.trim().split(/\s*,\s*/).filter(Boolean) : null;
        var sharpe = sharpeEl && sharpeEl.value.trim() ? parseFloat(sharpeEl.value, 10) : null;
        if (sharpe !== null && isNaN(sharpe)) sharpe = null;
        var payload = {
          risk_tolerance: riskEl ? riskEl.value : void 0,
          industry_preferences: industries,
          sharpe_objective: sharpe,
          loss_aversion: lossEl ? lossEl.value : void 0,
          use_finance_data_for_recommendations: useFinanceEl ? useFinanceEl.checked : void 0
        };
        savePrefsBtn.disabled = true;
        saveRiskProfile(payload).then(function() {
          savePrefsBtn.textContent = "Saved";
          setTimeout(function() {
            savePrefsBtn.textContent = "Save preferences";
            savePrefsBtn.disabled = false;
          }, 1500);
        }).catch(function(err) {
          alert(err.message || "Failed to save preferences");
          savePrefsBtn.disabled = false;
        });
      });
    }
    fetchLatest(1, true).then(function(data) {
      renderList(listEl, statusEl, data, 1);
      var hasRun = data && data.run;
      var hasItems = data && data.items && data.items.length > 0;
      if (summaryEl) {
        if (hasRun && (hasItems || data && data.portfolio)) renderSummary(summaryEl, data);
        else renderSummary(summaryEl, null);
      }
    }).catch(function() {
      statusEl.textContent = "Could not load latest recommendations. Make sure you are logged in.";
      if (summaryEl) summaryEl.innerHTML = '<p class="muted">Log in and try again to see portfolio risk metrics here.</p>';
    });
    var runBtn = document.getElementById("rec-run-btn");
    if (runBtn) {
      runBtn.addEventListener("click", function() {
        statusEl.textContent = "Generating recommendations\u2026";
        runBtn.disabled = true;
        runRecommendations().then(function(data) {
          renderSummary(summaryEl, data);
          try {
            sessionStorage.removeItem(_NORTH_STAR_KEY);
          } catch (e) {
          }
          return fetchLatest(1, true);
        }).then(function(data) {
          renderList(listEl, statusEl, data, 1);
          renderNorthStarStripRec();
        }).catch(function(err) {
          alert(err.message || "Failed to run recommendations");
        }).finally(function() {
          runBtn.disabled = false;
        });
      });
    }
    listEl.addEventListener("click", function(e) {
      var explainBtn = e.target.closest(".rec-explain-btn");
      if (explainBtn) {
        var symbol = explainBtn.getAttribute("data-symbol") || "";
        var runId = listEl.getAttribute("data-run-id") || "";
        openExplainDrawer(listEl, runId, symbol);
        return;
      }
      var scoreBtn = e.target.closest(".rec-score-btn");
      if (scoreBtn) {
        var sym = scoreBtn.getAttribute("data-symbol") || "";
        var runId = listEl.getAttribute("data-run-id") || "";
        openScoreModal(runId, sym);
        return;
      }
      var prevBtn = e.target.closest(".rec-pagination-prev");
      if (prevBtn) {
        var page = parseInt(prevBtn.getAttribute("data-page"), 10) || 1;
        statusEl.textContent = "Loading page " + page + "\u2026";
        fetchLatest(page, true).then(function(data) {
          renderList(listEl, statusEl, data, page);
        }).catch(function() {
          statusEl.textContent = "Failed to load page.";
        });
        return;
      }
      var nextBtn = e.target.closest(".rec-pagination-next");
      if (nextBtn) {
        var page = parseInt(nextBtn.getAttribute("data-page"), 10) || 1;
        statusEl.textContent = "Loading page " + page + "\u2026";
        fetchLatest(page, true).then(function(data) {
          renderList(listEl, statusEl, data, page);
        }).catch(function() {
          statusEl.textContent = "Failed to load page.";
        });
      }
    });
    var closeBtn = document.getElementById("rec-explain-close");
    if (closeBtn) closeBtn.addEventListener("click", closeExplainDrawer);
    var backdrop = document.getElementById("rec-explain-backdrop");
    if (backdrop) backdrop.addEventListener("click", closeExplainDrawer);
    var scoreCloseBtn = document.getElementById("rec-score-modal-close");
    if (scoreCloseBtn) scoreCloseBtn.addEventListener("click", closeScoreModal);
    var scoreBackdrop = document.querySelector(".rec-score-modal-backdrop");
    if (scoreBackdrop) scoreBackdrop.addEventListener("click", closeScoreModal);
    document.addEventListener("keydown", function(ev) {
      if (ev.key === "Escape") {
        if (document.getElementById("rec-score-modal-wrap") && document.getElementById("rec-score-modal-wrap").style.display === "block") {
          closeScoreModal();
        }
      }
    });
  }
  function fetchSurplusForStrip() {
    var gw = API || "";
    var expBase = typeof window !== "undefined" && window.EXPENSE_API_BASE ? window.EXPENSE_API_BASE : "";
    var base = gw || expBase || "";
    return fetch(base + "/api/v1/surplus", { headers: getAuthHeaders() }).then(function(r) {
      return r.ok ? r.json() : null;
    }).catch(function() {
      return null;
    });
  }
  var _NORTH_STAR_KEY = "pocketii_north_star_v1";
  var _NORTH_STAR_TTL = 5 * 60 * 1e3;
  function _sectorGapNorthStar(prefs, sectorRows) {
    if (!sectorRows || !sectorRows.length) return null;
    var prefsList = (prefs || []).map(function(p) {
      return String(p).toLowerCase().trim();
    }).filter(Boolean);
    function matchPct(pref) {
      var best = 0;
      sectorRows.forEach(function(s) {
        var name = String(s.name != null ? s.name : s.sector || "").toLowerCase();
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
      prefsList.forEach(function(pref) {
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
    sectorRows.forEach(function(s) {
      var name = String(s.name != null ? s.name : s.sector || "");
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
  function fetchNorthStarBundleRec() {
    try {
      var raw = sessionStorage.getItem(_NORTH_STAR_KEY);
      if (raw) {
        var o = JSON.parse(raw);
        if (o && o.data && o.ts && Date.now() - o.ts <= _NORTH_STAR_TTL) {
          return Promise.resolve(o.data);
        }
      }
    } catch (e) {
    }
    var h = getAuthHeaders();
    return Promise.all([
      fetch(API + "/api/v1/risk-profile", { headers: h }).then(function(r) {
        return r.ok ? r.json() : {};
      }),
      fetch(API + "/api/v1/portfolio/sector-breakdown", { headers: h }).then(function(r) {
        return r.ok ? r.json() : null;
      }),
      fetch(API + "/api/v1/recommendations/latest?page=1&page_size=1", { headers: h }).then(function(r) {
        return r.ok ? r.json() : null;
      }),
      fetchSurplusForStrip()
    ]).then(function(parts) {
      var risk = parts[0] || {};
      var sec = parts[1];
      var rec = parts[2];
      var surplus = parts[3];
      var sectors = sec && sec.sectors ? sec.sectors : [];
      var gap = _sectorGapNorthStar(risk.industry_preferences || [], sectors);
      var topSym = "";
      if (rec && rec.items && rec.items.length) topSym = (rec.items[0].symbol || "").toUpperCase();
      var inv = surplus ? parseFloat(surplus.investable_surplus || 0) : NaN;
      var data = { gap, topSymbol: topSym, surplus: isFinite(inv) ? inv : null };
      try {
        sessionStorage.setItem(_NORTH_STAR_KEY, JSON.stringify({ ts: Date.now(), data }));
      } catch (e2) {
      }
      return data;
    });
  }
  function renderNorthStarStripRec() {
    var strip = document.getElementById("rec-north-star-strip");
    var text = document.getElementById("rec-north-star-text");
    var link = document.getElementById("rec-north-star-link");
    if (!strip || !text) return;
    fetchNorthStarBundleRec().then(function(data) {
      if (!data) {
        strip.style.display = "none";
        return;
      }
      var parts = [];
      if (isFinite(data.surplus) && data.surplus > 0) {
        parts.push("Roughly $" + Math.round(data.surplus).toLocaleString("en-US") + " is available after bills and goals.");
      }
      if (data.gap) {
        parts.push("Your portfolio shows the largest gap vs a simple target split in " + data.gap.label + " (~" + data.gap.gapPct + " points).");
      }
      if (data.topSymbol) {
        parts.push("We ranked " + data.topSymbol + " first on your latest run\u2014see below for context (not a recommendation to trade).");
      }
      if (!parts.length) {
        strip.style.display = "none";
        return;
      }
      text.textContent = parts.join(" ");
      if (link) {
        link.style.display = data.topSymbol ? "inline" : "none";
        link.setAttribute("href", "#recommendations-results");
      }
      strip.style.display = "block";
    }).catch(function() {
      if (strip) strip.style.display = "none";
    });
  }
  function renderRecFinanceStrip(surplus) {
    var strip = document.getElementById("rec-finance-strip");
    var text = document.getElementById("rec-finance-text");
    if (!strip || !text || !surplus) return;
    var s = parseFloat(surplus.investable_surplus || 0);
    var fmt = function(n) {
      return "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    };
    if (s > 0) {
      text.textContent = "You have approximately " + fmt(s) + " available this month after your bills and goals.";
    } else if (s < 0) {
      text.textContent = "Your tracked spending exceeded income by " + fmt(Math.abs(s)) + " this month. This is informational only.";
      strip.style.borderLeftColor = "#e53e3e";
    } else {
      return;
    }
    strip.style.display = "block";
  }
  function renderSurplusWaterfall(surplus) {
    var card = document.getElementById("rec-surplus-waterfall-card");
    var listEl = document.getElementById("rec-surplus-waterfall-list");
    var summaryEl = document.getElementById("rec-surplus-waterfall-summary");
    var emptyEl = document.getElementById("rec-surplus-waterfall-empty");
    if (!card || !listEl || !summaryEl || !emptyEl) return;
    var fmt = function(n) {
      var x = Number(n);
      if (!isFinite(x)) return "\u2014";
      return "$" + Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    };
    card.style.display = "block";
    listEl.innerHTML = "";
    summaryEl.textContent = "";
    emptyEl.style.display = "none";
    if (!surplus || typeof surplus !== "object") {
      emptyEl.style.display = "block";
      summaryEl.textContent = "";
      return;
    }
    var inv = parseFloat(surplus.investable_surplus);
    var wf = surplus.waterfall;
    if (!wf || !wf.length) {
      emptyEl.style.display = "block";
      return;
    }
    wf.forEach(function(row) {
      var li = document.createElement("li");
      var isExpense = row.type === "expense";
      var isDeficit = row.type === "deficit";
      li.className = "rec-surplus-waterfall-row";
      if (isExpense) li.classList.add("rec-surplus-waterfall-row--out");
      if (row.type === "surplus" || isDeficit) li.classList.add("rec-surplus-waterfall-row--result");
      var label = document.createElement("span");
      label.className = "rec-surplus-waterfall-label";
      label.textContent = row.label || "";
      var amt = document.createElement("span");
      amt.className = "rec-surplus-waterfall-amt";
      var a = Number(row.amount);
      if (isExpense && isFinite(a)) {
        amt.textContent = "\u2212" + fmt(a);
      } else {
        amt.textContent = (isDeficit && isFinite(a) && a < 0 ? "\u2212" : "") + fmt(isFinite(a) ? a : 0);
      }
      li.appendChild(label);
      li.appendChild(amt);
      listEl.appendChild(li);
    });
    summaryEl.classList.remove("rec-surplus-waterfall-summary--warn", "rec-surplus-waterfall-summary--muted");
    if (isFinite(inv) && inv > 0) {
      summaryEl.textContent = "After these steps, about " + fmt(inv) + " may be genuinely yours to consider for long-term investing\u2014only if it fits your plan and cash needs. This is informational, not a recommendation to invest.";
    } else if (isFinite(inv) && inv < 0) {
      summaryEl.textContent = "By these estimates, tracked spending and commitments exceed income this period. Surplus-based suggestions may be limited until cash flow improves. Not financial advice.";
      summaryEl.classList.add("rec-surplus-waterfall-summary--warn");
    } else {
      summaryEl.textContent = "Little or no surplus remains in this estimate after bills, variable spending, goals, and irregular reserves. That is common; numbers update as you add data.";
      summaryEl.classList.add("rec-surplus-waterfall-summary--muted");
    }
  }
  function applyPageState(pageState) {
    recState.pageState = pageState || "";
    document.body.classList.remove("rec-page-steady", "rec-page-volatile", "rec-page-first-run", "rec-page-active");
    var steadyBanner = document.getElementById("rec-steady-banner");
    var volatileBanner = document.getElementById("rec-volatile-banner");
    var firstRunBanner = document.getElementById("rec-first-run-banner");
    if (steadyBanner) steadyBanner.style.display = "none";
    if (volatileBanner) volatileBanner.style.display = "none";
    if (firstRunBanner) firstRunBanner.style.display = "none";
    if (pageState === "steady" && steadyBanner) {
      steadyBanner.style.display = "block";
      document.body.classList.add("rec-page-steady");
    } else if (pageState === "volatile" && volatileBanner) {
      volatileBanner.style.display = "block";
      document.body.classList.add("rec-page-volatile");
    } else if (pageState === "first_run" && firstRunBanner) {
      firstRunBanner.style.display = "block";
      document.body.classList.add("rec-page-first-run");
    } else if (pageState === "active") {
      document.body.classList.add("rec-page-active");
    }
  }
  function fetchLatestDigest() {
    return fetch(API + "/api/v1/recommendations/digest/latest", { headers: getAuthHeaders() }).then(function(r) {
      return r.ok ? r.json() : null;
    }).catch(function() {
      return null;
    });
  }
  function renderDigestCard(data) {
    var card = document.getElementById("rec-digest-card");
    var weekEl = document.getElementById("rec-digest-week");
    var headlineEl = document.getElementById("rec-digest-headline");
    var bodyEl = document.getElementById("rec-digest-body");
    if (!card || !data || !data.digest) return;
    var d = data.digest;
    if (weekEl) weekEl.textContent = d.week_start_date ? "Week of " + d.week_start_date : "";
    if (headlineEl) headlineEl.textContent = d.headline || "";
    if (bodyEl) bodyEl.textContent = d.body_text || "";
    card.style.display = "block";
  }
  var _origFetchLatest = fetchLatest;
  fetchLatest = function(page, enrich) {
    return _origFetchLatest(page, enrich).then(function(data) {
      if (data && data.page_state) {
        applyPageState(data.page_state);
      } else {
        applyPageState("");
      }
      return data;
    });
  };
  function fetchWatchlist() {
    return fetch(API + "/api/v1/watchlist", { headers: getAuthHeaders() }).then(function(r) {
      return r.ok ? r.json() : null;
    }).catch(function() {
      return null;
    });
  }
  function renderWatchlist(data) {
    var el = document.getElementById("watchlist-list");
    if (!el) return;
    if (!data || !data.items || !data.items.length) {
      el.innerHTML = '<p class="muted" style="font-size:0.875rem;">No symbols on your watchlist yet. Click "+ Add" to track a symbol.</p>';
      return;
    }
    var html = '<ul style="list-style:none;padding:0;margin:0;">';
    data.items.forEach(function(item) {
      html += '<li style="display:flex;align-items:center;justify-content:space-between;padding:0.5rem 0;border-bottom:1px solid var(--border);">';
      html += "<div>";
      html += '<strong style="margin-right:0.5rem;">' + escapeHtml(item.symbol) + "</strong>";
      if (item.target_price) {
        html += '<span class="muted" style="font-size:0.8125rem;">' + item.direction + " $" + Number(item.target_price).toFixed(2) + "</span>";
      }
      if (item.notes) html += '<span class="muted" style="font-size:0.8125rem;margin-left:0.5rem;">' + escapeHtml(item.notes) + "</span>";
      html += "</div>";
      html += '<button type="button" class="btn btn-ghost watchlist-remove" data-id="' + item.watchlist_id + '" style="font-size:0.75rem;padding:0.1rem 0.4rem;">Remove</button>';
      html += "</li>";
    });
    html += "</ul>";
    el.innerHTML = html;
    el.querySelectorAll(".watchlist-remove").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var id = btn.getAttribute("data-id");
        if (!id || !confirm("Remove from watchlist?")) return;
        fetch(API + "/api/v1/watchlist/" + id, { method: "DELETE", headers: getAuthHeaders() }).then(function() {
          return fetchWatchlist();
        }).then(renderWatchlist).catch(function() {
          alert("Failed to remove");
        });
      });
    });
  }
  function initWatchlist() {
    fetchWatchlist().then(renderWatchlist);
    var addBtn = document.getElementById("watchlist-add-btn");
    var wrap = document.getElementById("watchlist-modal-wrap");
    var backdrop = document.getElementById("watchlist-modal-backdrop");
    var cancelBtn = document.getElementById("watchlist-modal-cancel");
    var form = document.getElementById("watchlist-add-form");
    if (addBtn && wrap) addBtn.addEventListener("click", function() {
      wrap.style.display = "block";
      wrap.setAttribute("aria-hidden", "false");
    });
    if (backdrop) backdrop.addEventListener("click", function() {
      wrap.style.display = "none";
      wrap.setAttribute("aria-hidden", "true");
    });
    if (cancelBtn) cancelBtn.addEventListener("click", function() {
      wrap.style.display = "none";
      wrap.setAttribute("aria-hidden", "true");
    });
    if (form) {
      form.addEventListener("submit", function(e) {
        e.preventDefault();
        var sym = (document.getElementById("watchlist-symbol").value || "").trim().toUpperCase();
        var price = parseFloat(document.getElementById("watchlist-price").value) || null;
        var dir = document.getElementById("watchlist-direction").value || "below";
        var notes = (document.getElementById("watchlist-notes").value || "").trim() || null;
        if (!sym) return;
        var headers = getAuthHeaders();
        headers["Content-Type"] = "application/json";
        fetch(API + "/api/v1/watchlist", {
          method: "POST",
          headers,
          body: JSON.stringify({ symbol: sym, target_price: price, direction: dir, notes })
        }).then(function(r) {
          return r.ok ? r.json() : Promise.reject("Failed");
        }).then(function() {
          wrap.style.display = "none";
          form.reset();
          fetchWatchlist().then(renderWatchlist);
        }).catch(function() {
          alert("Failed to add to watchlist");
        });
      });
    }
  }
  var _mcChartInstance = null;
  function runMonteCarlo() {
    var initial = parseFloat(document.getElementById("mc-initial").value) || 1e4;
    var monthly = parseFloat(document.getElementById("mc-monthly").value) || 500;
    var years = parseInt(document.getElementById("mc-years").value) || 20;
    var ret = parseFloat(document.getElementById("mc-return").value) || 7;
    var goal = parseFloat(document.getElementById("mc-goal").value) || null;
    var url = API + "/api/v1/scenario/monte-carlo?initial_value=" + initial + "&monthly_contribution=" + monthly + "&years=" + years + "&return_pct=" + ret;
    if (goal) url += "&goal_amount=" + goal;
    return fetch(url, { headers: getAuthHeaders() }).then(function(r) {
      return r.ok ? r.json() : null;
    }).catch(function() {
      return null;
    });
  }
  function renderMonteCarlo(data) {
    if (!data) return;
    var resultsEl = document.getElementById("mc-results");
    var statsEl = document.getElementById("mc-stats");
    var chartEl = document.getElementById("mc-chart");
    var goalProbEl = document.getElementById("mc-goal-prob");
    if (resultsEl) resultsEl.style.display = "block";
    var fmt = function(n) {
      return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    };
    if (statsEl) {
      var stats = [
        { label: "Pessimistic (P5)", value: fmt(data.p5), color: "#e53e3e" },
        { label: "Low (P25)", value: fmt(data.p25), color: "#ecc94b" },
        { label: "Median (P50)", value: fmt(data.p50), color: "#38a169" },
        { label: "High (P75)", value: fmt(data.p75), color: "#3182ce" },
        { label: "Optimistic (P95)", value: fmt(data.p95), color: "#805ad5" }
      ];
      statsEl.innerHTML = stats.map(function(s) {
        return '<div style="background:var(--surface-alt,#f8fafc);border-radius:6px;padding:0.5rem 0.75rem;text-align:center;"><div style="font-size:0.75rem;color:var(--text-muted);">' + s.label + '</div><div style="font-weight:700;color:' + s.color + ';font-size:1rem;">' + s.value + "</div></div>";
      }).join("");
    }
    if (goalProbEl && data.goal_probability != null) {
      goalProbEl.textContent = "Estimated probability of reaching your goal: " + data.goal_probability + "% (based on these assumptions).";
      goalProbEl.style.display = "block";
    }
    if (chartEl && typeof ApexCharts !== "undefined" && data.sample_paths && data.sample_paths.length) {
      if (_mcChartInstance) {
        try {
          _mcChartInstance.destroy();
        } catch (e) {
        }
        _mcChartInstance = null;
      }
      chartEl.innerHTML = "";
      var mcYears = data.assumptions ? data.assumptions.years : 20;
      var labels = Array.from({ length: data.months + 1 }, function(_, i) {
        return i % 12 === 0 ? "Year " + Math.floor(i / 12) : "";
      });
      var series = data.sample_paths.slice(0, 10).map(function(path, idx) {
        return { name: "Path " + (idx + 1), data: path };
      });
      _mcChartInstance = new ApexCharts(chartEl, {
        chart: { type: "line", height: 260, toolbar: { show: false }, animations: { enabled: false } },
        series,
        xaxis: { categories: labels, labels: { rotate: 0 } },
        yaxis: { labels: { formatter: function(v) {
          return "$" + Math.round(v / 1e3) + "k";
        } } },
        stroke: { width: 1, curve: "smooth" },
        legend: { show: false },
        colors: Array(10).fill("#94a3b8"),
        dataLabels: { enabled: false },
        tooltip: { enabled: false }
      });
      _mcChartInstance.render();
    }
  }
  function initMonteCarlo() {
    var btn = document.getElementById("mc-run-btn");
    if (!btn) return;
    btn.addEventListener("click", function() {
      btn.disabled = true;
      btn.textContent = "Running...";
      runMonteCarlo().then(function(data) {
        renderMonteCarlo(data);
        btn.disabled = false;
        btn.textContent = "Run projection";
      }).catch(function() {
        btn.disabled = false;
        btn.textContent = "Run projection";
        alert("Projection failed. Please try again.");
      });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function() {
      init();
      fetchSurplusForStrip().then(function(s) {
        renderRecFinanceStrip(s);
        renderSurplusWaterfall(s);
      });
      renderNorthStarStripRec();
      fetchLatestDigest().then(renderDigestCard);
      initWatchlist();
      initMonteCarlo();
    });
  } else {
    init();
    fetchSurplusForStrip().then(function(s) {
      renderRecFinanceStrip(s);
      renderSurplusWaterfall(s);
    });
    renderNorthStarStripRec();
    fetchLatestDigest().then(renderDigestCard);
    initWatchlist();
    initMonteCarlo();
  }
})();
