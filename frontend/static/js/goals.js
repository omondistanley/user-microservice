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
            container.innerHTML = '<p class="text-slate-500 dark:text-slate-400 text-sm">Loading…</p>';
            var self = this;
            return this.list().then(function(goals) {
                if (!goals.length) {
                    container.innerHTML = '<p class="text-slate-500 dark:text-slate-400 text-sm">No goals yet. Add one to get started.</p>';
                    if (options.onTotals) options.onTotals({ totalSaved: 0, totalTarget: 0, count: 0 });
                    return;
                }
                var totalSaved = 0, totalTarget = 0;
                return Promise.all(goals.map(function(g) {
                    return self.getProgress(g.goal_id).then(function(p) {
                        return { goal: g, progress: p };
                    }).catch(function() { return { goal: g, progress: null }; });
                })).then(function(withProgress) {
                    var html = '';
                    withProgress.forEach(function(x) {
                        var g = x.goal;
                        var p = x.progress;
                        var target = Number(g.target_amount) || 0;
                        var current = (p && p.current_amount != null) ? Number(p.current_amount) : (Number(g.start_amount) || 0);
                        totalTarget += target;
                        totalSaved += current;
                        var pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
                        html += '<a href="/goals/' + encodeURIComponent(g.goal_id) + '" class="block bg-white dark:bg-slate-800/50 rounded-2xl p-4 border border-slate-100 dark:border-slate-700 hover:border-primary/30">' +
                            '<div class="flex items-center gap-3">' +
                            '<div class="size-10 rounded-xl bg-slate-100 dark:bg-slate-700 flex items-center justify-center">' +
                            '<span class="material-symbols-outlined text-slate-600 dark:text-slate-400">savings</span></div>' +
                            '<div class="flex-1 min-w-0">' +
                            '<p class="text-sm font-bold text-slate-900 dark:text-slate-100 truncate">' + (g.name || 'Goal') + '</p>' +
                            '<p class="text-xs text-slate-500 dark:text-slate-400">$' + current.toLocaleString() + ' / $' + target.toLocaleString() + '</p>' +
                            '</div></div>' +
                            '<div class="mt-3 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">' +
                            '<div class="h-full rounded-full bg-primary" style="width:' + pct + '%"></div></div></a>';
                    });
                    container.innerHTML = html;
                    if (options.onTotals) options.onTotals({ totalSaved: totalSaved, totalTarget: totalTarget, count: goals.length });
                });
            }).catch(function(err) {
                container.innerHTML = '<p class="text-red-500 text-sm">' + (err.message || 'Failed to load goals') + '</p>';
            });
        },
    };
})();
