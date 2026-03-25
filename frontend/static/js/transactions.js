"use strict";
(function() {
  "use strict";
  var API = window.API_BASE || "";
  var page = 1;
  var pageSize = 25;
  function headers() {
    return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
  }
  function load() {
    var tbody = document.getElementById("tx-tbody");
    var status = document.getElementById("tx-status");
    var pag = document.getElementById("tx-pagination");
    if (!tbody) return;
    var et = document.getElementById("tx-entry-type");
    var search = document.getElementById("tx-search");
    var typeQ = et && et.value ? "&entry_type=" + encodeURIComponent(et.value) : "";
    var searchQ = search && search.value.trim() ? "&search=" + encodeURIComponent(search.value.trim()) : "";
    var url = API + "/api/v1/transactions?page=" + page + "&page_size=" + pageSize + typeQ + searchQ;
    if (status) status.textContent = "Loading\u2026";
    fetch(url, { headers: headers() }).then(function(r) {
      if (!r.ok) throw new Error("Failed to load");
      return r.json();
    }).then(function(data) {
      var items = data && data.items || [];
      tbody.innerHTML = items.map(function(row) {
        var amt = row.amount != null ? Number(row.amount) : 0;
        var sign = row.entry_type === "income" ? "+" : "\u2212";
        var cls = row.entry_type === "income" ? "text-emerald-600 dark:text-emerald-400" : "text-slate-900 dark:text-white";
        var desc = row.description || row.category_name || "\u2014";
        var link = row.entry_type === "expense" ? '<a href="/expenses/' + encodeURIComponent(row.entry_id) + '" class="text-[#135bec] hover:underline">' + esc(desc) + "</a>" : esc(desc);
        return '<tr class="border-t border-slate-100 dark:border-slate-800"><td class="px-4 py-3 capitalize">' + esc(row.entry_type || "") + '</td><td class="px-4 py-3 whitespace-nowrap">' + esc(row.occurred_on || "") + '</td><td class="px-4 py-3">' + link + '</td><td class="px-4 py-3 text-right font-semibold ' + cls + '">' + sign + "$" + Math.abs(amt).toFixed(2) + "</td></tr>";
      }).join("") || '<tr><td colspan="4" class="px-4 py-8 text-center text-slate-500">No transactions yet.</td></tr>';
      var total = data && data.total || 0;
      var pages = Math.max(1, Math.ceil(total / pageSize));
      if (status) status.textContent = total + " total";
      if (pag) {
        pag.innerHTML = '<span class="text-sm text-slate-500">Page ' + page + " / " + pages + "</span>" + (page > 1 ? ' <button type="button" class="tx-prev px-3 py-1 rounded border text-sm">Prev</button>' : "") + (page < pages ? ' <button type="button" class="tx-next px-3 py-1 rounded border text-sm">Next</button>' : "");
        var prev = pag.querySelector(".tx-prev");
        var next = pag.querySelector(".tx-next");
        if (prev) prev.onclick = function() {
          page--;
          load();
        };
        if (next) next.onclick = function() {
          page++;
          load();
        };
      }
    }).catch(function() {
      if (status) status.textContent = "Could not load transactions.";
      tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-6 text-center text-rose-600">Error loading data</td></tr>';
    });
  }
  function esc(s) {
    if (s == null) return "";
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  document.addEventListener("DOMContentLoaded", function() {
    load();
    var r = document.getElementById("tx-refresh");
    if (r) r.addEventListener("click", function() {
      page = 1;
      load();
    });
    var et = document.getElementById("tx-entry-type");
    if (et) et.addEventListener("change", function() {
      page = 1;
      load();
    });
    var sx = document.getElementById("tx-search");
    if (sx) {
      var t;
      sx.addEventListener("input", function() {
        clearTimeout(t);
        t = setTimeout(function() {
          page = 1;
          load();
        }, 350);
      });
    }
  });
})();
