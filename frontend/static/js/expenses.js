"use strict";
(function() {
  "use strict";
  var API = window.EXPENSE_API_BASE !== void 0 && window.EXPENSE_API_BASE !== "" ? window.EXPENSE_API_BASE : window.API_BASE || "";
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
      if (!r.ok) {
        return r.json().catch(function() {
          return null;
        }).then(function(data) {
          var detail = data && (data.detail || data.message || data.error);
          throw new Error(detail || r.statusText || "Request failed");
        });
      }
      return r.json().catch(function() {
        return null;
      });
    });
  }
  function escapeHtml(value) {
    return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  var CATEGORY_DEFAULT_ICON = {
    food: "restaurant",
    transportation: "directions_car",
    travel: "flight",
    utilities: "lightbulb",
    entertainment: "movie",
    health: "medical_services",
    shopping: "shopping_bag",
    other: "inventory_2"
  };
  var KEYWORD_ICON = [
    [/ice\s*cream|gelato|froyo/i, "icecream"],
    [/pizza/i, "lunch_dining"],
    [/burger|mcdonald|wendys|five guys/i, "lunch_dining"],
    [/coffee|starbucks|espresso|latte/i, "local_cafe"],
    [/grocery|whole foods|trader|supermarket|costco/i, "shopping_cart"],
    [/gas|fuel|shell|chevron|exxon|petrol/i, "local_gas_station"],
    [/uber|lyft|taxi|rideshare/i, "local_taxi"],
    [/parking|toll/i, "local_parking"],
    [/flight|airline|delta|united|southwest/i, "flight"],
    [/hotel|airbnb|lodging/i, "hotel"],
    [/restaurant|dining|cafe|sushi|thai|mexican/i, "restaurant"],
    [/gym|fitness|peloton/i, "fitness_center"],
    [/pharmacy|cvs|walgreens|rx/i, "medical_services"],
    [/netflix|spotify|hulu|streaming/i, "tv"],
    [/electric|water\s*bill|internet|comcast|att|verizon/i, "wifi"]
  ];
  function materialIcon(name) {
    return '<span class="material-symbols-rounded" aria-hidden="true">' + name + "</span>";
  }
  function pickExpenseIcon(item) {
    var cat = (item.category_name || item.category || "").toLowerCase().trim();
    var text = ((item.description || "") + " " + (item.name || "") + " " + cat).toLowerCase();
    for (var i = 0; i < KEYWORD_ICON.length; i++) {
      if (KEYWORD_ICON[i][0].test(text)) return KEYWORD_ICON[i][1];
    }
    var catKey = cat.replace(/[^a-z]/g, "");
    if (catKey && CATEGORY_DEFAULT_ICON[catKey]) return CATEGORY_DEFAULT_ICON[catKey];
    return CATEGORY_DEFAULT_ICON.other;
  }
  window.Expenses = {
    getTags: function() {
      return request("/api/v1/tags");
    },
    createTag: function(name) {
      return request("/api/v1/tags", { method: "POST", body: { name } });
    },
    fillTagSuggestions: function(inputEl, datalistEl) {
      if (!inputEl || !datalistEl || !window.Expenses.getTags) return Promise.resolve();
      return window.Expenses.getTags().then(function(tags) {
        if (!Array.isArray(tags)) return;
        datalistEl.innerHTML = tags.map(function(t) {
          return '<option value="' + escapeHtml(t.name || "") + '"></option>';
        }).join("");
      });
    },
    parseTagInput: function(value) {
      if (!value) return [];
      var seen = {};
      return value.split(",").map(function(v) {
        return v.trim();
      }).filter(function(v) {
        var key = v.toLowerCase();
        if (!key || seen[key]) return false;
        seen[key] = true;
        return true;
      });
    },
    getCategories: function() {
      return request("/api/v1/categories");
    },
    createCategory: function(name) {
      return request("/api/v1/categories", { method: "POST", body: { name } });
    },
    fillCategorySelect: function(selectEl, selectedName) {
      if (!selectEl || !window.Expenses.getCategories) return Promise.resolve();
      return window.Expenses.getCategories().then(function(cats) {
        if (!Array.isArray(cats)) return;
        selectEl.innerHTML = '<option value="">Select category</option>' + cats.map(function(c) {
          var n = c.name || "";
          var sel = selectedName && (c.name || "").toLowerCase() === (selectedName || "").toLowerCase() ? " selected" : "";
          return '<option value="' + n + '"' + sel + ">" + n + "</option>";
        }).join("");
      });
    },
    formatAmount: function(val) {
      if (val == null || val === "") return "";
      var n = parseFloat(val, 10);
      return isNaN(n) ? "" : n.toFixed(2);
    },
    buildListQuery: function(opts) {
      opts = opts || {};
      var q = [];
      if (opts.date_from) q.push("date_from=" + encodeURIComponent(opts.date_from));
      if (opts.date_to) q.push("date_to=" + encodeURIComponent(opts.date_to));
      if (opts.category) q.push("category=" + encodeURIComponent(opts.category));
      if (opts.tag_id) q.push("tag_id=" + encodeURIComponent(opts.tag_id));
      if (opts.tag) q.push("tag=" + encodeURIComponent(opts.tag));
      if (opts.min_amount != null && opts.min_amount !== "") q.push("min_amount=" + encodeURIComponent(opts.min_amount));
      if (opts.max_amount != null && opts.max_amount !== "") q.push("max_amount=" + encodeURIComponent(opts.max_amount));
      if (opts.page) q.push("page=" + encodeURIComponent(opts.page));
      if (opts.page_size) q.push("page_size=" + encodeURIComponent(opts.page_size));
      return q.length ? "?" + q.join("&") : "";
    },
    loadList: function(containerEl, balanceEl, opts, paginationCallback) {
      if (!containerEl) return;
      containerEl.innerHTML = "Loading\u2026";
      var query = window.Expenses.buildListQuery(opts || {});
      request("/api/v1/expenses" + query).then(function(data) {
        var list = data && data.items ? data.items : Array.isArray(data) ? data : [];
        if (list.length === 0) {
          containerEl.innerHTML = "No expenses yet. Add one to get started.";
          containerEl.classList.add("empty-state");
          if (balanceEl) balanceEl.textContent = "Running balance: 0.00";
          return;
        }
        containerEl.classList.remove("empty-state");
        var grouped = {};
        list.forEach(function(item) {
          var d = item.date || "";
          if (!grouped[d]) grouped[d] = [];
          grouped[d].push(item);
        });
        var dateLabels = Object.keys(grouped).sort().reverse();
        var html = "";
        dateLabels.forEach(function(dateKey) {
          var items = grouped[dateKey];
          var label = dateKey;
          if (dateKey.length >= 10) {
            var parts = dateKey.split("-");
            if (parts.length === 3) {
              var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
              var mi = parseInt(parts[1], 10) - 1;
              label = (months[mi] || parts[1]) + " " + parts[2] + ", " + parts[0];
            }
          }
          html += '<div class="expense-date-group"><h3 class="expense-group-date">' + label + '</h3><ul class="expense-list">';
          items.forEach(function(item) {
            var amt = item.amount != null ? item.amount : item.value;
            var name = (item.description || item.name || "").trim() || (item.category_name || item.category || "");
            if (!name) name = "\u2014";
            var id = (item.expense_id || "").trim();
            var amtStr = window.Expenses && window.Expenses.formatAmount ? window.Expenses.formatAmount(amt) : amt != null ? Number(amt).toFixed(2) : "";
            var link = id ? '<a href="/expenses/' + id + '" class="expense-item-link">' : "";
            var linkEnd = id ? "</a>" : "";
            var sourceBadge = item.source === "plaid" ? ' <span class="badge badge-plaid">From bank</span>' : "";
            var tagBadges = "";
            if (Array.isArray(item.tags) && item.tags.length) {
              tagBadges = ' <span class="expense-item-tags">' + item.tags.map(function(tag) {
                return '<span class="tag-badge">' + escapeHtml(tag.name || tag.slug || "") + "</span>";
              }).join(" ") + "</span>";
            }
            var icon = '<span class="expense-item-emoji" aria-hidden="true">' + materialIcon(pickExpenseIcon(item)) + "</span> ";
            html += "<li>" + link + icon + '<span class="expense-item-name">' + escapeHtml(name) + "</span>" + sourceBadge + tagBadges + ' <strong class="expense-item-amount">' + amtStr + "</strong>" + linkEnd + "</li>";
          });
          html += "</ul></div>";
        });
        containerEl.innerHTML = html;
        if (balanceEl && list.length) {
          var first = list[0];
          var bal = first.balance_after != null ? first.balance_after : "";
          var balStr = window.Expenses && window.Expenses.formatAmount ? window.Expenses.formatAmount(bal) : bal !== "" ? Number(bal).toFixed(2) : "";
          balanceEl.textContent = balStr !== "" ? "Running balance: " + balStr : "";
        }
        var total = data && data.total != null ? data.total : list.length;
        var page = opts && opts.page ? parseInt(opts.page, 10) : 1;
        var pageSize = opts && opts.page_size ? parseInt(opts.page_size, 10) : 20;
        if (typeof paginationCallback === "function") paginationCallback(total, page, pageSize);
      }).catch(function(err) {
        containerEl.innerHTML = "Could not load expenses. (" + (err.message || "API error") + ")";
        containerEl.classList.add("empty-state");
        if (balanceEl) balanceEl.textContent = "";
        if (typeof paginationCallback === "function") paginationCallback(0, 1, 20);
      });
    },
    getSummary: function(groupBy, dateFrom, dateTo, convertTo) {
      var q = ["group_by=" + encodeURIComponent(groupBy || "category")];
      if (dateFrom) q.push("date_from=" + encodeURIComponent(dateFrom));
      if (dateTo) q.push("date_to=" + encodeURIComponent(dateTo));
      if (convertTo) q.push("convert_to=" + encodeURIComponent(convertTo));
      return request("/api/v1/expenses/summary?" + q.join("&"));
    },
    getBalanceHistory: function(dateFrom, dateTo, groupBy) {
      var q = [];
      if (dateFrom) q.push("date_from=" + encodeURIComponent(dateFrom));
      if (dateTo) q.push("date_to=" + encodeURIComponent(dateTo));
      if (groupBy) q.push("group_by=" + encodeURIComponent(groupBy));
      return request("/api/v1/expenses/balance/history?" + q.join("&"));
    },
    loadBalance: function(balanceEl) {
      if (!balanceEl) return;
      request("/api/v1/expenses/balance").then(function(data) {
        var bal = data && data.balance_after != null ? data.balance_after : null;
        var str = bal != null && window.Expenses.formatAmount ? window.Expenses.formatAmount(bal) : bal != null ? Number(bal).toFixed(2) : "";
        balanceEl.textContent = str !== "" ? "Running balance: " + str : "";
      }).catch(function() {
        balanceEl.textContent = "";
      });
    },
    add: function(payload, idempotencyKey) {
      var options = { method: "POST", body: payload };
      if (idempotencyKey) options.headers = { "Idempotency-Key": idempotencyKey };
      return request("/api/v1/expenses", options);
    },
    getExpense: function(expenseId) {
      return request("/api/v1/expenses/" + encodeURIComponent(expenseId));
    },
    updateExpense: function(expenseId, payload) {
      return request("/api/v1/expenses/" + encodeURIComponent(expenseId), {
        method: "PATCH",
        body: payload
      });
    },
    deleteExpense: function(expenseId) {
      var headers = {};
      if (window.Auth && window.Auth.getAuthHeaders) {
        Object.assign(headers, window.Auth.getAuthHeaders());
      }
      return fetch(API + "/api/v1/expenses/" + encodeURIComponent(expenseId), {
        method: "DELETE",
        headers
      }).then(function(r) {
        if (!r.ok) throw new Error(r.statusText || "Request failed");
      });
    },
    listReceipts: function(expenseId) {
      return request("/api/v1/expenses/" + encodeURIComponent(expenseId) + "/receipts");
    },
    uploadReceipt: function(expenseId, file) {
      var form = new FormData();
      form.append("file", file);
      var headers = {};
      if (window.Auth && window.Auth.getAuthHeaders) {
        Object.assign(headers, window.Auth.getAuthHeaders());
      }
      return fetch(API + "/api/v1/expenses/" + encodeURIComponent(expenseId) + "/receipts", {
        method: "POST",
        headers,
        body: form
      }).then(function(r) {
        if (!r.ok) throw new Error(r.statusText || "Upload failed");
        return r.json().catch(function() {
          return null;
        });
      });
    },
    downloadReceiptUrl: function(receiptId) {
      return API + "/api/v1/receipts/" + encodeURIComponent(receiptId) + "/download";
    },
    downloadReceipt: function(receiptId, fileName) {
      var headers = {};
      if (window.Auth && window.Auth.getAuthHeaders) {
        Object.assign(headers, window.Auth.getAuthHeaders());
      }
      return fetch(API + "/api/v1/receipts/" + encodeURIComponent(receiptId) + "/download", { headers }).then(function(r) {
        if (!r.ok) throw new Error(r.statusText || "Download failed");
        return r.blob();
      }).then(function(blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = fileName || "receipt";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    },
    deleteReceipt: function(receiptId) {
      var headers = {};
      if (window.Auth && window.Auth.getAuthHeaders) {
        Object.assign(headers, window.Auth.getAuthHeaders());
      }
      return fetch(API + "/api/v1/receipts/" + encodeURIComponent(receiptId), {
        method: "DELETE",
        headers
      }).then(function(r) {
        if (!r.ok) throw new Error(r.statusText || "Delete failed");
      });
    },
    runReceiptOcr: function(receiptId) {
      return request("/api/v1/receipts/" + encodeURIComponent(receiptId) + "/ocr", {
        method: "POST"
      });
    },
    getReceiptOcr: function(receiptId) {
      return request("/api/v1/receipts/" + encodeURIComponent(receiptId) + "/ocr");
    },
    applyReceiptExtraction: function(receiptId) {
      return request("/api/v1/receipts/" + encodeURIComponent(receiptId) + "/apply-extraction", {
        method: "POST"
      });
    }
  };
})();
