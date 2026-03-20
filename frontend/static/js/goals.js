/**
 * Phase 4: Savings goals — fetch from GET /api/v1/goals and progress.
 */
(function() {
    'use strict';
    var API = window.API_BASE || '';

    function authHeaders() {
        return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeCurrency(cur) {
        var s = String(cur || '').trim().toUpperCase();
        return s ? s.slice(0, 3) : 'USD';
    }

    window.Goals = {
        _goalsById: {},
        _lastRender: null,

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

        updateGoal: function(goalId, payload) {
            var headers = authHeaders();
            headers['Content-Type'] = 'application/json';
            return fetch(API + '/api/v1/goals/' + encodeURIComponent(goalId), {
                method: 'PATCH',
                headers: headers,
                body: JSON.stringify(payload)
            }).then(function(r) {
                if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail || 'Failed to update goal'); });
                return r.json();
            });
        },

        closeEditModal: function() {
            var wrap = document.getElementById('goals-edit-modal-wrap');
            if (!wrap) return;
            wrap.style.display = 'none';
            wrap.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        },

        openEditModal: function(goal) {
            var wrap = document.getElementById('goals-edit-modal-wrap');
            if (!wrap || !goal) return;

            var idEl = document.getElementById('goals-edit-goal-id');
            var nameEl = document.getElementById('goals-edit-name');
            var targetAmountEl = document.getElementById('goals-edit-target-amount');
            var targetCurrencyEl = document.getElementById('goals-edit-target-currency');
            var targetDateEl = document.getElementById('goals-edit-target-date');
            var startAmountEl = document.getElementById('goals-edit-start-amount');
            var msgEl = document.getElementById('goals-edit-msg');

            if (idEl) idEl.value = goal.goal_id;
            if (nameEl) nameEl.value = goal.name || '';
            if (targetAmountEl) targetAmountEl.value = Number(goal.target_amount || 0);
            if (targetCurrencyEl) targetCurrencyEl.value = normalizeCurrency(goal.target_currency);
            if (targetDateEl) targetDateEl.value = goal.target_date ? String(goal.target_date).slice(0, 10) : '';
            if (startAmountEl) startAmountEl.value = Number(goal.start_amount || 0);
            if (msgEl) {
                msgEl.style.display = 'none';
                msgEl.textContent = '';
            }

            wrap.style.display = '';
            wrap.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        },

        _ensureModalBindings: function(options) {
            // Bind once per page load; renderList may run multiple times.
            if (this._modalBound) return;
            this._modalBound = true;

            var wrap = document.getElementById('goals-edit-modal-wrap');
            var backdrop = document.getElementById('goals-edit-backdrop');
            var cancelBtn = document.getElementById('goals-edit-cancel');
            var form = document.getElementById('goals-edit-form');
            var msgEl = document.getElementById('goals-edit-msg');
            var saveBtn = document.getElementById('goals-edit-save');

            if (backdrop && wrap) {
                backdrop.addEventListener('click', function() {
                    window.Goals.closeEditModal();
                });
            }
            if (cancelBtn) {
                cancelBtn.addEventListener('click', function() {
                    window.Goals.closeEditModal();
                });
            }
            if (form) {
                form.addEventListener('submit', function(e) {
                    e.preventDefault();
                    if (!window.Goals._lastRender) return;

                    var idEl = document.getElementById('goals-edit-goal-id');
                    var goalId = idEl ? idEl.value : null;
                    if (!goalId) return;

                    if (msgEl) {
                        msgEl.style.display = 'none';
                        msgEl.textContent = '';
                    }
                    if (saveBtn) saveBtn.disabled = true;

                    var nameVal = document.getElementById('goals-edit-name') ? document.getElementById('goals-edit-name').value : '';
                    var targetAmountVal = document.getElementById('goals-edit-target-amount') ? document.getElementById('goals-edit-target-amount').value : '';
                    var targetCurrencyVal = document.getElementById('goals-edit-target-currency') ? document.getElementById('goals-edit-target-currency').value : '';
                    var targetDateVal = document.getElementById('goals-edit-target-date') ? document.getElementById('goals-edit-target-date').value : '';
                    var startAmountVal = document.getElementById('goals-edit-start-amount') ? document.getElementById('goals-edit-start-amount').value : '';

                    var payload = {
                        name: String(nameVal || '').trim(),
                        target_amount: parseFloat(targetAmountVal),
                        target_currency: normalizeCurrency(targetCurrencyVal),
                        start_amount: parseFloat(startAmountVal)
                    };

                    if (targetDateVal && String(targetDateVal).trim()) payload.target_date = String(targetDateVal).slice(0, 10);
                    if (!payload.name) {
                        if (msgEl) {
                            msgEl.style.display = 'block';
                            msgEl.textContent = 'Goal name is required.';
                        }
                        if (saveBtn) saveBtn.disabled = false;
                        return;
                    }
                    if (isNaN(payload.target_amount) || payload.target_amount < 0) {
                        if (msgEl) {
                            msgEl.style.display = 'block';
                            msgEl.textContent = 'Target amount must be a valid number.';
                        }
                        if (saveBtn) saveBtn.disabled = false;
                        return;
                    }
                    if (isNaN(payload.start_amount) || payload.start_amount < 0) {
                        if (msgEl) {
                            msgEl.style.display = 'block';
                            msgEl.textContent = 'Starting amount must be a valid number.';
                        }
                        if (saveBtn) saveBtn.disabled = false;
                        return;
                    }

                    window.Goals.updateGoal(goalId, payload).then(function() {
                        window.Goals.closeEditModal();
                        // Refresh list + totals
                        var lr = window.Goals._lastRender;
                        return window.Goals.renderList(lr.containerId, lr.options);
                    }).catch(function(err) {
                        if (msgEl) {
                            msgEl.style.display = 'block';
                            msgEl.textContent = err && err.message ? err.message : 'Failed to update goal.';
                        }
                    }).finally(function() {
                        if (saveBtn) saveBtn.disabled = false;
                    });
                });
            }

            document.addEventListener('keydown', function(ev) {
                if (ev.key !== 'Escape') return;
                var wrapEl = document.getElementById('goals-edit-modal-wrap');
                if (wrapEl && wrapEl.style && wrapEl.style.display !== 'none') {
                    window.Goals.closeEditModal();
                }
            });
        },

        renderList: function(containerId, options) {
            options = options || {};
            var container = document.getElementById(containerId);
            if (!container) return Promise.resolve();
            this._lastRender = { containerId: containerId, options: options };
            container.innerHTML = '<p class="muted" style="font-size:14px;">Loading…</p>';
            var self = this;
            return this.list().then(function(goals) {
                if (!goals.length) {
                    container.innerHTML = '<p class="muted" style="font-size:14px;">No goals yet. Add one to get started.</p>';
                    if (options.onTotals) options.onTotals({ totalSaved: 0, totalTarget: 0, count: 0 });
                    return;
                }
                var totalSaved = 0, totalTarget = 0;
                self._goalsById = {};
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
                        var name = escapeHtml(g.name || 'Goal');
                        var left = target - current;
                        var leftText = left <= 0 ? 'Target reached' : (fmtMoney(left) + ' to go');
                        var fillClass = pct >= 100 ? 'green' : (pct >= 75 ? 'amber' : 'green');
                        var goalId = String(g.goal_id);
                        self._goalsById[goalId] = g;
                        html += '<div class="card goal-card-budget" role="button" tabindex="0" data-goal-id="' + escapeHtml(goalId) + '" style="text-decoration:none;color:inherit;display:block;cursor:pointer;">' +
                            '<div class="goal-card-budget-inner" style="display:flex;flex-direction:column;">' +
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
                            '<div style="display:flex;justify-content:flex-end;margin-top:12px;">' +
                            '<button type="button" class="btn btn-ghost btn-sm goal-edit-btn" data-goal-id="' + escapeHtml(goalId) + '" aria-label="Edit goal">Edit</button>' +
                            '</div>' +
                            '</div>' +
                            '</div>';
                    });
                    container.innerHTML = html;
                    // Bind modal actions + card click handling (once)
                    self._ensureModalBindings();
                    if (!container._goalsCardBound) {
                        container._goalsCardBound = true;
                        container.addEventListener('click', function(e) {
                            var editBtn = e.target && e.target.closest ? e.target.closest('.goal-edit-btn') : null;
                            if (editBtn) {
                                e.preventDefault();
                                e.stopPropagation();
                                var gid = editBtn.getAttribute('data-goal-id') || '';
                                var goal = self._goalsById[String(gid)] || null;
                                self.openEditModal(goal);
                                return;
                            }
                            var card = e.target && e.target.closest ? e.target.closest('.goal-card-budget') : null;
                            if (card) {
                                var goalId = card.getAttribute('data-goal-id');
                                if (goalId) window.location.href = '/goals/' + encodeURIComponent(goalId);
                            }
                        });
                        container.addEventListener('keydown', function(e) {
                            if (e.key !== 'Enter' && e.key !== ' ') return;
                            var target = e.target && e.target.closest ? e.target.closest('.goal-card-budget') : null;
                            if (!target) return;
                            var goalId = target.getAttribute('data-goal-id');
                            if (goalId) {
                                e.preventDefault();
                                window.location.href = '/goals/' + encodeURIComponent(goalId);
                            }
                        });
                    }
                    if (options.onTotals) options.onTotals({ totalSaved: totalSaved, totalTarget: totalTarget, count: goals.length });
                });
            }).catch(function(err) {
                container.innerHTML = '<p style="color:var(--rose);font-size:14px;">' + (err.message || 'Failed to load goals') + '</p>';
            });
        },
    };
})();
