(function() {
    'use strict';

    var API = window.API_BASE || '';
    var started = false;
    var pollHandle = null;

    function request(path, options) {
        options = options || {};
        options.headers = options.headers || {};
        if (window.Auth && window.Auth.getAuthHeaders) {
            Object.assign(options.headers, window.Auth.getAuthHeaders());
        }
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }
        var doFetch = (window.Auth && window.Auth.requestWithRefresh)
            ? function() { return window.Auth.requestWithRefresh(API + path, options); }
            : function() { return fetch(API + path, options); };
        return doFetch().then(function(r) {
            if (!r.ok) throw new Error(r.statusText || 'Request failed');
            return r.json().catch(function() { return null; });
        });
    }

    function notificationItemsHtml(items) {
        if (!Array.isArray(items) || items.length === 0) {
            return 'No notifications yet.';
        }
        return items.map(function(item) {
            var stateClass = item.is_read ? 'is-read' : 'is-unread';
            var createdAt = item.created_at ? String(item.created_at).replace('T', ' ').slice(0, 16) : '';
            return (
                '<div class="notification-item ' + stateClass + '" data-notification-id="' + item.notification_id + '">' +
                    '<div class="notification-item-title">' + (item.title || 'Notification') + '</div>' +
                    '<div class="notification-item-body">' + (item.body || '') + '</div>' +
                    '<div class="notification-item-meta">' + createdAt + '</div>' +
                '</div>'
            );
        }).join('');
    }

    function renderNotificationList(items) {
        var html = notificationItemsHtml(items);
        var listEl = document.getElementById('notifications-list');
        var topbarList = document.getElementById('topbar-notifications-list');
        if (listEl) listEl.innerHTML = html;
        if (topbarList) topbarList.innerHTML = html;
    }

    function renderUnreadCount(unread) {
        var n = Number(unread || 0);
        var countEl = document.getElementById('notifications-unread-count');
        if (countEl) {
            if (n > 0) {
                countEl.textContent = String(n);
                countEl.style.display = 'inline-block';
            } else {
                countEl.textContent = '0';
                countEl.style.display = 'none';
            }
        }
        var sidebarBadge = document.getElementById('sidebar-notif-badge');
        if (sidebarBadge) {
            if (n > 0) {
                sidebarBadge.textContent = n > 99 ? '99+' : String(n);
                sidebarBadge.style.display = 'inline';
            } else {
                sidebarBadge.style.display = 'none';
            }
        }
        var topbarBadge = document.getElementById('topbar-notif-badge');
        if (topbarBadge) {
            topbarBadge.style.display = n > 0 ? 'block' : 'none';
        }
    }

    function refresh() {
        return request('/api/v1/notifications?page=1&page_size=10').then(function(payload) {
            renderNotificationList(payload && payload.items ? payload.items : []);
            renderUnreadCount(payload && payload.unread != null ? payload.unread : 0);
            return payload;
        }).catch(function() {
            renderNotificationList([]);
            renderUnreadCount(0);
            return null;
        });
    }

    function bindEvents() {
        var toggle = document.getElementById('notifications-toggle');
        var dropdown = document.getElementById('notifications-dropdown');
        var markAllBtn = document.getElementById('notifications-mark-all');
        var listEl = document.getElementById('notifications-list');

        if (toggle && dropdown) {
            toggle.addEventListener('click', function(e) {
                e.preventDefault();
                var open = dropdown.style.display === 'block';
                dropdown.style.display = open ? 'none' : 'block';
                if (!open) refresh();
            });
            document.addEventListener('click', function(e) {
                if (dropdown.style.display === 'block' && !dropdown.contains(e.target) && !toggle.contains(e.target)) {
                    dropdown.style.display = 'none';
                }
            });
        }

        if (markAllBtn) {
            markAllBtn.addEventListener('click', function() {
                request('/api/v1/notifications/read-all', { method: 'PATCH' }).then(function() {
                    refresh();
                }).catch(function() {});
            });
        }

        function bindListReadHandler(el) {
            if (!el) return;
            el.addEventListener('click', function(e) {
                var target = e.target;
                if (!target) return;
                var row = target.closest ? target.closest('.notification-item') : null;
                if (!row) return;
                var notificationId = row.getAttribute('data-notification-id');
                if (!notificationId) return;
                request('/api/v1/notifications/' + encodeURIComponent(notificationId) + '/read', { method: 'PATCH' })
                    .then(function() { refresh(); })
                    .catch(function() {});
            });
        }
        bindListReadHandler(listEl);
        bindListReadHandler(document.getElementById('topbar-notifications-list'));

        var topbarMarkAll = document.getElementById('topbar-notif-mark-all');
        if (topbarMarkAll) {
            topbarMarkAll.addEventListener('click', function() {
                request('/api/v1/notifications/read-all', { method: 'PATCH' }).then(function() {
                    refresh();
                }).catch(function() {});
            });
        }
    }

    window.Notifications = {
        refresh: refresh,
        start: function() {
            if (started) return;
            started = true;
            bindEvents();
            refresh();
            pollHandle = window.setInterval(refresh, 30000);
        },
        stop: function() {
            if (pollHandle) {
                window.clearInterval(pollHandle);
                pollHandle = null;
            }
            started = false;
        },
    };
})();
