"use strict";
(function() {
  "use strict";
  var API = window.BUDGET_API_BASE !== void 0 && window.BUDGET_API_BASE !== "" ? window.BUDGET_API_BASE : window.API_BASE || "";
  var CATEGORIES = [
    { code: 1, name: "Food" },
    { code: 2, name: "Transportation" },
    { code: 3, name: "Travel" },
    { code: 4, name: "Utilities" },
    { code: 5, name: "Entertainment" },
    { code: 6, name: "Health" },
    { code: 7, name: "Shopping" },
    { code: 8, name: "Other" }
  ];
  function request(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    if (window.Auth && window.Auth.getAuthHeaders) {
      Object.assign(options.headers, window.Auth.getAuthHeaders());
    }
    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    var doFetch = window.Auth && window.Auth.requestWithRefresh ? function() {
      return window.Auth.requestWithRefresh(API + path, options);
    } : function() {
      return fetch(API + path, options);
    };
    return doFetch().then(function(r) {
      if (!r.ok) throw new Error(r.statusText || "Request failed");
      return r.json().catch(function() {
        return null;
      });
    });
  }
  function formatAmount(val) {
    if (val == null || val === "") return "";
    var n = parseFloat(val, 10);
    return isNaN(n) ? "" : n.toFixed(2);
  }
  function formatDate(val) {
    if (!val) return "\u2014";
    var s = String(val).slice(0, 10);
    if (s.length >= 10) {
      var parts = s.split("-");
      if (parts.length === 3) {
        var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        var mi = parseInt(parts[1], 10) - 1;
        return (months[mi] || parts[1]) + " " + parts[2] + ", " + parts[0];
      }
    }
    return s;
  }
  window.Budgets = {
    getCategories: function() {
      return CATEGORIES;
    },
    fillCategorySelect: function(selectEl, selectedCode) {
      if (!selectEl) return;
      selectEl.innerHTML = '<option value="">Select category</option>' + CATEGORIES.map(function(c) {
        var sel = selectedCode != null && c.code === selectedCode ? " selected" : "";
        return '<option value="' + c.code + '"' + sel + ">" + c.name + "</option>";
      }).join("");
    },
    buildListQuery: function(opts) {
      opts = opts || {};
      var q = [];
      if (opts.category_code != null && opts.category_code !== "") q.push("category_code=" + encodeURIComponent(opts.category_code));
      if (opts.effective_date) q.push("effective_date=" + encodeURIComponent(opts.effective_date));
      if (opts.include_inactive) q.push("include_inactive=true");
      if (opts.page) q.push("page=" + encodeURIComponent(opts.page));
      if (opts.page_size) q.push("page_size=" + encodeURIComponent(opts.page_size));
      return q.length ? "?" + q.join("&") : "";
    },
    getList: function(params) {
      var query = this.buildListQuery(params || {});
      return request("/api/v1/budgets" + query);
    },
    getEffective: function(categoryCode, dateStr) {
      var q = "category_code=" + encodeURIComponent(categoryCode) + "&date=" + encodeURIComponent(dateStr);
      return request("/api/v1/budgets/effective?" + q);
    },
    create: function(payload) {
      return request("/api/v1/budgets", { method: "POST", body: payload });
    },
    getById: function(id) {
      return request("/api/v1/budgets/" + encodeURIComponent(id));
    },
    update: function(id, payload) {
      return request("/api/v1/budgets/" + encodeURIComponent(id), {
        method: "PATCH",
        body: payload
      });
    },
    delete: function(id) {
      var headers = {};
      if (window.Auth && window.Auth.getAuthHeaders) {
        Object.assign(headers, window.Auth.getAuthHeaders());
      }
      return fetch(API + "/api/v1/budgets/" + encodeURIComponent(id), {
        method: "DELETE",
        headers
      }).then(function(r) {
        if (!r.ok) throw new Error(r.statusText || "Delete failed");
      });
    },
    formatAmount,
    formatDate,
    loadList: function(containerEl, opts, paginationCallback) {
      if (!containerEl) return;
      containerEl.innerHTML = "Loading\u2026";
      var self = this;
      this.getList(opts || {}).then(function(data) {
        var list = data && data.items ? data.items : [];
        var total = data && data.total != null ? data.total : 0;
        if (list.length === 0) {
          containerEl.innerHTML = "No budgets yet. Add one to get started.";
          containerEl.classList.add("empty-state");
          if (typeof paginationCallback === "function") paginationCallback(0, 1, opts && opts.page_size ? opts.page_size : 20);
          return;
        }
        containerEl.classList.remove("empty-state");
        var html = '<table class="budget-table"><thead><tr><th>Name</th><th>Category</th><th>Amount</th><th>Start</th><th>End</th><th>Actions</th></tr></thead><tbody>';
        list.forEach(function(item) {
          var id = (item.budget_id || "").trim();
          var name = (item.name || "").trim() || "\u2014";
          var cat = item.category_name || item.category_code || "\u2014";
          var amt = self.formatAmount(item.amount);
          var start = self.formatDate(item.start_date);
          var end = self.formatDate(item.end_date);
          var link = id ? '<a href="/budgets/' + id + '">View</a>' : "";
          var delBtn = id ? ' <button type="button" class="btn btn-secondary btn-sm budget-delete" data-id="' + id + '">Delete</button>' : "";
          html += "<tr><td>" + name + "</td><td>" + cat + "</td><td>" + amt + "</td><td>" + start + "</td><td>" + end + "</td><td>" + link + delBtn + "</td></tr>";
        });
        html += "</tbody></table>";
        containerEl.innerHTML = html;
        var page = opts && opts.page ? parseInt(opts.page, 10) : 1;
        var pageSize = opts && opts.page_size ? parseInt(opts.page_size, 10) : 20;
        if (typeof paginationCallback === "function") paginationCallback(total, page, pageSize);
        containerEl.querySelectorAll(".budget-delete").forEach(function(btn) {
          btn.addEventListener("click", function() {
            var bid = this.getAttribute("data-id");
            if (!bid || !confirm("Delete this budget?")) return;
            self.delete(bid).then(function() {
              self.loadList(containerEl, opts, paginationCallback);
            }).catch(function(err) {
              alert(err.message || "Delete failed");
            });
          });
        });
      }).catch(function(err) {
        containerEl.innerHTML = "Could not load budgets. (" + (err.message || "API error") + ")";
        containerEl.classList.add("empty-state");
        if (typeof paginationCallback === "function") paginationCallback(0, 1, 20);
      });
    }
  };
})();
