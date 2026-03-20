/**
 * Phase 4: Savings goals — fetch from GET /api/v1/goals and progress.
 */
(function() {
    'use strict';
    var API = window.API_BASE || '';

    function authHeaders() {
        return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
    }

    window.Goals = {
        list: function() {
            return fetch(API + '/api/v1/goals', { headers: authHeaders() })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.detail) throw new Error(data.detail);
                    return data.items || [];
                });
        },
        getProgress: function(goalId) {
            return fetch(API + '/api/v1/goals/' + encodeURIComponent(goalId) + '/progress', { headers: authHeaders() })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.detail) throw new Error(data.detail);
                    return data;
                });
        },
        renderList: function(containerId, options) {
            options = options || {};
            var container = document.getElementById(containerId);
            if (!container) return Promise.resolve();
            container.innerHTML = '<p class="muted" style="font-size:14px;">Loading…</p>';
            var self = this;
            return this.list().then(function(goals) {
                if (!goals.length) {
                    container.innerHTML = '<p class="muted" style="font-size:14px;">No goals yet. Add one to get started.</p>';
                    if (options.onTotals) options.onTotals({ totalSaved: 0, totalTarget: 0, count: 0 });
                    return;
                }
                var totalSaved = 0, totalTarget = 0;
                return Promise.all(goals.map(function(g) {
                    return self.getProgress(g.goal_id).then(function(p) {
                        return { goal: g, progress: p };
                    }).catch(function() { return { goal: g, progress: null }; });
                })).then(function(withProgress) {
                    function fmtMoney(n) {
                        var v = Number(n) || 0;
                        return '$' + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
                    var html = '';
                    withProgress.forEach(function(x) {
                        var g = x.goal;
                        var p = x.progress;
                        var target = Number(g.target_amount) || 0;
                        var current = (p && p.current_amount != null) ? Number(p.current_amount) : (Number(g.start_amount) || 0);
                        totalTarget += target;
                        totalSaved += current;
                        var pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
                        var name = (g.name || 'Goal').replace(/</g, '&lt;');
                        var left = target - current;
                        var leftText = left <= 0 ? 'Target reached' : (fmtMoney(left) + ' to go');
                        var fillClass = pct >= 100 ? 'green' : (pct >= 75 ? 'amber' : 'green');
                        html += '<a href="/goals/' + encodeURIComponent(g.goal_id) + '" class="card goal-card-budget" style="text-decoration:none;color:inherit;display:block;">' +
                            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">' +
                            '<div style="display:flex;align-items:center;gap:10px;">' +
                            '<div style="width:40px;height:40px;border-radius:10px;background:var(--s100);display:flex;align-items:center;justify-content:center;font-size:18px;">⭐</div>' +
                            '<span style="font-size:14px;font-weight:700;color:var(--text-primary);">' + name + '</span>' +
                            '</div>' +
                            '<span class="badge badge-emerald">' + pct + '%</span>' +
                            '</div>' +
                            '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">' +
                            '<span style="font-size:18px;font-weight:800;color:var(--text-primary);">' + fmtMoney(current) + '</span>' +
                            '<span style="font-size:12px;color:var(--text-muted);">of ' + fmtMoney(target) + '</span>' +
                            '</div>' +
                            '<div class="progress-bar"><div class="progress-fill ' + fillClass + '" style="width:' + pct + '%;"></div></div>' +
                            '<div style="font-size:12px;font-weight:500;margin-top:6px;color:var(--text-secondary);">' + leftText + '</div>' +
                            '</a>';
                    });
                    container.innerHTML = html;
                    if (options.onTotals) options.onTotals({ totalSaved: totalSaved, totalTarget: totalTarget, count: goals.length });
                });
            }).catch(function(err) {
                container.innerHTML = '<p style="color:var(--rose);font-size:14px;">' + (err.message || 'Failed to load goals') + '</p>';
            });
        },
    };
})();
