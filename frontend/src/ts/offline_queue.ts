// @ts-nocheck
/**
 * Phase 6: Offline queue for expense/income create. Replay with Idempotency-Key on reconnect.
 */
(function () {
    'use strict';
    var QUEUE_KEY = 'expense_offline_queue';
    var API = window.API_BASE || '';

    function authHeaders() {
        return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
    }

    function getQueue() {
        try {
            var raw = localStorage.getItem(QUEUE_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    function setQueue(arr) {
        try {
            localStorage.setItem(QUEUE_KEY, JSON.stringify(arr));
        } catch (e) {}
    }

    function generateId() {
        return 'offline-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
    }

    function enqueue(type, payload) {
        var id = generateId();
        var item = { id: id, type: type, payload: payload, status: 'pending', createdAt: new Date().toISOString() };
        var q = getQueue();
        q.push(item);
        setQueue(q);
        return id;
    }

    function updateStatus(id, status, err) {
        var q = getQueue();
        for (var i = 0; i < q.length; i++) {
            if (q[i].id === id) {
                q[i].status = status;
                if (err) q[i].error = err;
                break;
            }
        }
        setQueue(q);
    }

    function removeFromQueue(id) {
        var q = getQueue().filter(function (x) { return x.id !== id; });
        setQueue(q);
    }

    function replayOne(item) {
        var headers = Object.assign({ 'Content-Type': 'application/json', 'Idempotency-Key': item.id }, authHeaders());
        var url = API + '/api/v1/expenses';
        if (item.type === 'income') url = API + '/api/v1/income';
        return fetch(url, { method: 'POST', headers: headers, body: JSON.stringify(item.payload) })
            .then(function (r) {
                if (r.ok) {
                    updateStatus(item.id, 'synced');
                    removeFromQueue(item.id);
                    return true;
                }
                return r.json().then(function (d) {
                    updateStatus(item.id, 'failed', d.detail || r.statusText);
                    return false;
                });
            })
            .catch(function (e) {
                updateStatus(item.id, 'failed', e.message);
                return false;
            });
    }

    function replayAll() {
        var pending = getQueue().filter(function (x) { return x.status === 'pending'; });
        if (!pending.length) return Promise.resolve();
        return pending.reduce(function (p, item) {
            return p.then(function () { return replayOne(item); });
        }, Promise.resolve());
    }

    function onOnline() {
        replayAll();
    }

    if (typeof window !== 'undefined') {
        window.addEventListener('online', onOnline);
        if (navigator.onLine) setTimeout(onOnline, 500);
    }

    window.OfflineQueue = {
        enqueue: enqueue,
        getQueue: getQueue,
        replayAll: replayAll,
        updateStatus: updateStatus,
    };
})();
